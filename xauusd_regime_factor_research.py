from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import MetaTrader5 as mt5
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
import statsmodels.api as sm

from xauusd_calendar_geo_regime_analysis import (
    align_geo_dates_to_trading_days,
    build_daily_regime,
    build_geo_daily_flags,
    build_macro_daily_flags,
    extract_wiki_daily_texts,
    load_native_calendar,
)
from xauusd_regime_switching_grid_backtest import fetch_rates, initialize_mt5


ROOT = Path(__file__).resolve().parent
DEFAULT_CALENDAR_PATH = ROOT / "data" / "codex_native_calendar_majors.csv"
YAHOO_HEADERS = {"User-Agent": "Mozilla/5.0"}
YAHOO_SERIES = {
    "dxy": "DX-Y.NYB",
    "tnx": "^TNX",
    "tip": "TIP",
    "vix": "^VIX",
    "oil": "CL=F",
    "spx": "^GSPC",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Comprehensive XAUUSD regime-factor empirical study.")
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--timeframe", default="M15")
    parser.add_argument("--bars", type=int, default=30000)
    parser.add_argument(
        "--terminal-path",
        default=r"C:\MT5PortableCodex\terminal64.exe",
    )
    parser.add_argument(
        "--calendar-path",
        default=str(DEFAULT_CALENDAR_PATH),
    )
    parser.add_argument("--outdir", default="artifacts_xauusd_regime_factor_research")
    return parser.parse_args()


def build_session_features(raw_bars: pd.DataFrame) -> pd.DataFrame:
    bars = raw_bars.copy()
    bars["date"] = bars["time"].dt.floor("D")
    bars["hour"] = bars["time"].dt.hour
    bars["session"] = np.select(
        [
            bars["hour"].between(0, 7),
            bars["hour"].between(8, 15),
            bars["hour"].between(16, 23),
        ],
        ["asia", "europe", "us"],
        default="other",
    )
    bars = bars.loc[bars["session"] != "other"].copy()

    session = (
        bars.groupby(["date", "session"], as_index=False)
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            bar_count=("time", "size"),
        )
        .sort_values(["date", "session"])
        .reset_index(drop=True)
    )
    session["range"] = session["high"] - session["low"]
    session["body_ratio"] = (session["close"] - session["open"]).abs() / session["range"].replace(0, np.nan)

    pivot = session.pivot(index="date", columns="session")
    pivot.columns = [f"{metric}_{sess}" for metric, sess in pivot.columns]
    pivot = pivot.reset_index().sort_values("date").reset_index(drop=True)

    for sess in ["asia", "europe", "us"]:
        if f"range_{sess}" in pivot.columns:
            pivot[f"range_ratio_{sess}"] = (
                pivot[f"range_{sess}"]
                / pivot[f"range_{sess}"].shift(1).rolling(20, min_periods=10).median()
            )

    pivot["europe_break_asia"] = (
        (pivot["high_europe"] > pivot["high_asia"]) | (pivot["low_europe"] < pivot["low_asia"])
    )
    pivot["us_break_early"] = (
        (pivot["high_us"] > pivot[["high_asia", "high_europe"]].max(axis=1))
        | (pivot["low_us"] < pivot[["low_asia", "low_europe"]].min(axis=1))
    )
    pivot["asia_compression"] = pivot["range_ratio_asia"] <= 0.80
    pivot["asia_compression_plus_europe_break"] = pivot["asia_compression"] & pivot["europe_break_asia"]
    return pivot


def build_price_structure_features(daily: pd.DataFrame) -> pd.DataFrame:
    out = daily.copy().sort_values("date").reset_index(drop=True)
    out["prev_day_high"] = out["day_high"].shift(1)
    out["prev_day_low"] = out["day_low"].shift(1)
    out["prev_day_range_ratio"] = out["day_range"].shift(1) / out["prior20_range_median"]
    out["prev3_range_ratio"] = out["day_range"].shift(1).rolling(3, min_periods=3).mean() / out["prior20_range_median"]
    scale = out["prior20_range_median"].replace(0, np.nan)
    out["dist_to_prev_high_norm"] = (out["prev_day_high"] - out["day_open"]).abs() / scale
    out["dist_to_prev_low_norm"] = (out["day_open"] - out["prev_day_low"]).abs() / scale
    out["min_prev_extreme_dist_norm"] = out[["dist_to_prev_high_norm", "dist_to_prev_low_norm"]].min(axis=1)
    out["PREV_DAY_COMPRESSION"] = out["prev_day_range_ratio"] <= 0.85
    out["PREV3_DAY_COMPRESSION"] = out["prev3_range_ratio"] <= 0.90
    out["OPEN_NEAR_PREV_EXTREME"] = out["min_prev_extreme_dist_norm"] <= 0.25
    out["OPEN_OUTSIDE_PREV_RANGE"] = (out["day_open"] > out["prev_day_high"]) | (out["day_open"] < out["prev_day_low"])
    return out


def fetch_yahoo_series(symbol: str, cache_dir: Path) -> pd.DataFrame:
    cache_path = cache_dir / f"{symbol.replace('^', 'idx_').replace('=', '_')}.json"
    if cache_path.exists():
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    else:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=2y&interval=1d"
        response = requests.get(url, headers=YAHOO_HEADERS, timeout=30)
        response.raise_for_status()
        payload = response.json()
        cache_path.write_text(json.dumps(payload), encoding="utf-8")

    result = payload["chart"]["result"][0]
    timestamps = result.get("timestamp", [])
    close = result["indicators"]["quote"][0].get("close", [])
    frame = pd.DataFrame({"timestamp": timestamps, "close": close})
    frame = frame.dropna().copy()
    frame["date"] = pd.to_datetime(frame["timestamp"], unit="s").dt.floor("D")
    frame = frame[["date", "close"]].rename(columns={"close": symbol})
    frame = frame.drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
    return frame


def build_cross_asset_features(start_date: pd.Timestamp, end_date: pd.Timestamp, outdir: Path) -> pd.DataFrame:
    cache_dir = outdir / "yahoo_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    merged = None
    for key, symbol in YAHOO_SERIES.items():
        series = fetch_yahoo_series(symbol, cache_dir).rename(columns={symbol: key})
        merged = series if merged is None else merged.merge(series, on="date", how="outer")
    merged = merged.sort_values("date").reset_index(drop=True)
    merged = merged.loc[(merged["date"] >= start_date - pd.Timedelta(days=10)) & (merged["date"] <= end_date)].copy()
    merged = merged.ffill()

    merged["dxy_ret"] = merged["dxy"].pct_change()
    merged["tnx_change"] = merged["tnx"].diff()
    merged["tip_ret"] = merged["tip"].pct_change()
    merged["vix_ret"] = merged["vix"].pct_change()
    merged["oil_ret"] = merged["oil"].pct_change()
    merged["spx_ret"] = merged["spx"].pct_change()

    def q80(series: pd.Series) -> float:
        valid = series.abs().dropna()
        return float(valid.quantile(0.80)) if not valid.empty else math.inf

    thresholds = {
        "DOLLAR_SHOCK": q80(merged["dxy_ret"]),
        "YIELD_SHOCK": q80(merged["tnx_change"]),
        "REALRATE_PROXY_SHOCK": q80(merged["tip_ret"]),
        "VIX_SHOCK": q80(merged["vix_ret"]),
        "OIL_SHOCK": q80(merged["oil_ret"]),
        "SPX_SHOCK": q80(merged["spx_ret"]),
    }
    for label, threshold in thresholds.items():
        base_col = label.lower().replace("_shock", "")
        metric_col = {
            "DOLLAR_SHOCK": "dxy_ret",
            "YIELD_SHOCK": "tnx_change",
            "REALRATE_PROXY_SHOCK": "tip_ret",
            "VIX_SHOCK": "vix_ret",
            "OIL_SHOCK": "oil_ret",
            "SPX_SHOCK": "spx_ret",
        }[label]
        merged[label] = merged[metric_col].abs() >= threshold

    merged["CROSS_ASSET_ANY_SHOCK"] = merged[
        ["DOLLAR_SHOCK", "YIELD_SHOCK", "REALRATE_PROXY_SHOCK", "VIX_SHOCK", "OIL_SHOCK", "SPX_SHOCK"]
    ].any(axis=1)
    merged["DOLLAR_YIELD_CONFLUENCE"] = merged["DOLLAR_SHOCK"] & merged["YIELD_SHOCK"]
    merged.to_csv(outdir / "cross_asset_daily.csv", index=False)
    return merged


def build_weekend_geo_flag(geo_daily: pd.DataFrame) -> pd.DataFrame:
    out = geo_daily.copy()

    def has_weekend(source_dates: str) -> bool:
        if not isinstance(source_dates, str) or not source_dates:
            return False
        for value in source_dates.split(","):
            stamp = pd.to_datetime(value, errors="coerce")
            if pd.isna(stamp):
                continue
            if stamp.weekday() >= 5:
                return True
        return False

    out["WEEKEND_GEO_CARRY"] = out["source_dates"].apply(has_weekend)
    return out


def summarize_factor(frame: pd.DataFrame, label: str, flag_col: str) -> dict | None:
    if flag_col not in frame.columns:
        return None
    event = frame.loc[frame[flag_col] & frame["range_ratio"].notna()].copy()
    baseline = frame.loc[(~frame[flag_col]) & frame["range_ratio"].notna()].copy()
    if event.empty or baseline.empty:
        return None
    avg = float(event["range_ratio"].mean())
    base = float(baseline["range_ratio"].mean())
    reg = float(event["regime_score"].mean())
    base_reg = float(baseline["regime_score"].mean())
    return {
        "label": label,
        "event_days": int(len(event)),
        "avg_range_ratio": avg,
        "median_range_ratio": float(event["range_ratio"].median()),
        "baseline_range_ratio": base,
        "range_lift_pct": (avg / base - 1.0) * 100.0 if base else np.nan,
        "avg_regime_score": reg,
        "baseline_regime_score": base_reg,
        "regime_lift_pct": (reg / base_reg - 1.0) * 100.0 if base_reg else np.nan,
        "high_vol_rate": float(event["high_vol_day"].mean()),
        "trend_day_rate": float(event["trend_day"].mean()),
        "avg_abs_return_pct": float(event["abs_return_pct"].mean()),
    }


def roc_auc_score_manual(y_true: pd.Series, y_score: pd.Series) -> float:
    valid = pd.DataFrame({"y": y_true, "score": y_score}).dropna()
    if valid["y"].nunique() < 2:
        return float("nan")
    valid["rank"] = valid["score"].rank(method="average")
    pos = valid.loc[valid["y"] == 1]
    n_pos = len(pos)
    n_neg = len(valid) - n_pos
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    auc = (pos["rank"].sum() - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)
    return float(auc)


def fit_models(
    frame: pd.DataFrame,
    features: list[str],
    outdir: Path,
    prefix: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = frame.loc[frame[features + ["high_vol_day", "trend_day", "regime_score"]].notna().all(axis=1)].copy()
    split_idx = max(20, int(len(df) * 0.70))
    train = df.iloc[:split_idx].copy()
    test = df.iloc[split_idx:].copy()

    X_train = sm.add_constant(train[features].astype(float), has_constant="add")
    X_test = sm.add_constant(test[features].astype(float), has_constant="add")
    X_full = sm.add_constant(df[features].astype(float), has_constant="add")

    high_model = sm.GLM(train["high_vol_day"].astype(float), X_train, family=sm.families.Binomial()).fit()
    trend_model = sm.GLM(train["trend_day"].astype(float), X_train, family=sm.families.Binomial()).fit()
    regime_model = sm.OLS(train["regime_score"].astype(float), X_train).fit(cov_type="HC1")

    high_pred = high_model.predict(X_test) if not test.empty else pd.Series(dtype=float)
    trend_pred = trend_model.predict(X_test) if not test.empty else pd.Series(dtype=float)
    regime_pred = regime_model.predict(X_test) if not test.empty else pd.Series(dtype=float)

    summary_rows = [
        {
            "model": f"{prefix}_high_vol_logit",
            "train_obs": len(train),
            "test_obs": len(test),
            "oos_auc": roc_auc_score_manual(test["high_vol_day"], high_pred) if not test.empty else np.nan,
            "train_pseudo_r2": 1.0 - high_model.deviance / high_model.null_deviance if high_model.null_deviance else np.nan,
        },
        {
            "model": f"{prefix}_trend_day_logit",
            "train_obs": len(train),
            "test_obs": len(test),
            "oos_auc": roc_auc_score_manual(test["trend_day"], trend_pred) if not test.empty else np.nan,
            "train_pseudo_r2": 1.0 - trend_model.deviance / trend_model.null_deviance if trend_model.null_deviance else np.nan,
        },
        {
            "model": f"{prefix}_regime_score_ols",
            "train_obs": len(train),
            "test_obs": len(test),
            "oos_corr": float(pd.Series(regime_pred).corr(test["regime_score"])) if not test.empty else np.nan,
            "train_r2": float(regime_model.rsquared),
        },
    ]

    coef_rows = []
    for model_name, model in [
        (f"{prefix}_high_vol_logit", sm.GLM(df["high_vol_day"].astype(float), X_full, family=sm.families.Binomial()).fit()),
        (f"{prefix}_trend_day_logit", sm.GLM(df["trend_day"].astype(float), X_full, family=sm.families.Binomial()).fit()),
        (f"{prefix}_regime_score_ols", sm.OLS(df["regime_score"].astype(float), X_full).fit(cov_type="HC1")),
    ]:
        for feature in ["const"] + features:
            coef_rows.append(
                {
                    "model": model_name,
                    "feature": feature,
                    "coef": float(model.params.get(feature, np.nan)),
                    "pvalue": float(model.pvalues.get(feature, np.nan)),
                }
            )

    summary_df = pd.DataFrame(summary_rows)
    coef_df = pd.DataFrame(coef_rows)
    summary_df.to_csv(outdir / f"{prefix}_model_summary.csv", index=False)
    coef_df.to_csv(outdir / f"{prefix}_model_coefficients.csv", index=False)
    return summary_df, coef_df


def plot_top_factors(df: pd.DataFrame, title: str, outpath: Path) -> None:
    if df.empty:
        return
    plot_df = df.sort_values("range_lift_pct", ascending=True).tail(12)
    fig, ax = plt.subplots(figsize=(10, 6.4))
    ax.barh(plot_df["label"], plot_df["range_lift_pct"], color="#946c2f")
    ax.set_title(title)
    ax.set_xlabel("Range Lift vs Baseline (%)")
    ax.grid(axis="x", alpha=0.25)
    fig.tight_layout()
    fig.savefig(outpath, dpi=160)
    plt.close(fig)


def plot_coefficients(df: pd.DataFrame, model_name: str, title: str, outpath: Path) -> None:
    subset = df.loc[(df["model"] == model_name) & (df["feature"] != "const")].copy()
    if subset.empty:
        return
    subset = subset.sort_values("coef", ascending=True)
    fig, ax = plt.subplots(figsize=(10, 6.0))
    colors = ["#0f766e" if value > 0 else "#b45309" for value in subset["coef"]]
    ax.barh(subset["feature"], subset["coef"], color=colors)
    ax.set_title(title)
    ax.set_xlabel("Coefficient")
    ax.grid(axis="x", alpha=0.25)
    fig.tight_layout()
    fig.savefig(outpath, dpi=160)
    plt.close(fig)


def main() -> None:
    args = parse_args()
    outdir = ROOT / args.outdir
    outdir.mkdir(parents=True, exist_ok=True)
    cache_dir = outdir / "wiki_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    initialize_mt5(args.terminal_path)
    try:
        raw_bars, point, contract_size = fetch_rates(args.symbol, args.timeframe, args.bars)
    finally:
        mt5.shutdown()

    daily_regime_full = build_daily_regime(raw_bars)
    daily_regime_full = build_price_structure_features(daily_regime_full)
    session_features = build_session_features(raw_bars)
    full = daily_regime_full.merge(session_features, on="date", how="left")

    cross = build_cross_asset_features(full["date"].min(), full["date"].max(), outdir)
    full = full.merge(cross, on="date", how="left")

    native_calendar = load_native_calendar(args.calendar_path)
    overlap_start = pd.Timestamp("2025-10-01")
    overlap_end = min(full["date"].max(), pd.Timestamp("2026-03-31"))
    macro_daily = build_macro_daily_flags(native_calendar, overlap_start, overlap_end, outdir)

    wiki_daily_raw = extract_wiki_daily_texts(overlap_start, overlap_end, cache_dir)
    wiki_daily = align_geo_dates_to_trading_days(wiki_daily_raw, pd.Index(full.loc[full["date"].between(overlap_start, overlap_end), "date"].drop_duplicates().sort_values()))
    geo_daily, geo_examples = build_geo_daily_flags(wiki_daily)
    geo_daily = build_weekend_geo_flag(geo_daily)

    overlap = full.loc[(full["date"] >= overlap_start) & (full["date"] <= overlap_end)].copy()
    overlap = overlap.merge(macro_daily, on="date", how="left").merge(geo_daily, on="date", how="left")

    bool_cols = [
        "PREV_DAY_COMPRESSION",
        "PREV3_DAY_COMPRESSION",
        "OPEN_NEAR_PREV_EXTREME",
        "OPEN_OUTSIDE_PREV_RANGE",
        "asia_compression",
        "europe_break_asia",
        "us_break_early",
        "asia_compression_plus_europe_break",
        "DOLLAR_SHOCK",
        "YIELD_SHOCK",
        "REALRATE_PROXY_SHOCK",
        "VIX_SHOCK",
        "OIL_SHOCK",
        "SPX_SHOCK",
        "CROSS_ASSET_ANY_SHOCK",
        "DOLLAR_YIELD_CONFLUENCE",
        "WEEKEND_GEO_CARRY",
    ]
    bool_cols.extend([col for col in overlap.columns if col.endswith("_SHOCK") or col.startswith("US_") or col in ["FED_POLICY", "ECB_POLICY", "BOJ_POLICY", "USD_HIGH_ANY"]])

    for col in bool_cols:
        if col in full.columns:
            full[col] = full[col].fillna(False).astype(bool)
        if col in overlap.columns:
            overlap[col] = overlap[col].fillna(False).astype(bool)

    full.to_csv(outdir / "xau_regime_full_dataset.csv", index=False)
    overlap.to_csv(outdir / "xau_regime_overlap_dataset.csv", index=False)
    geo_examples.to_csv(outdir / "geo_theme_examples.csv", index=False)

    full_factor_cols = [
        "PREV_DAY_COMPRESSION",
        "PREV3_DAY_COMPRESSION",
        "OPEN_NEAR_PREV_EXTREME",
        "OPEN_OUTSIDE_PREV_RANGE",
        "asia_compression",
        "europe_break_asia",
        "us_break_early",
        "asia_compression_plus_europe_break",
        "DOLLAR_SHOCK",
        "YIELD_SHOCK",
        "REALRATE_PROXY_SHOCK",
        "VIX_SHOCK",
        "OIL_SHOCK",
        "SPX_SHOCK",
        "CROSS_ASSET_ANY_SHOCK",
        "DOLLAR_YIELD_CONFLUENCE",
    ]
    overlap_extra_cols = [
        "FED_POLICY",
        "US_INFLATION",
        "US_LABOR_MAJOR",
        "US_LABOR_SECONDARY",
        "US_GROWTH_ACTIVITY",
        "US_TREASURY_OIL",
        "ECB_POLICY",
        "BOJ_POLICY",
        "USD_HIGH_ANY",
        "GEO_ANY_SHOCK",
        "GEO_MIDDLE_EAST_SHOCK",
        "GEO_RUSSIA_UKRAINE_SHOCK",
        "GEO_US_CHINA_TAIWAN_TRADE_SHOCK",
        "GEO_KOREA_PENINSULA_SHOCK",
        "GEO_INDIA_PAKISTAN_SHOCK",
        "WEEKEND_GEO_CARRY",
    ]

    full_rows = []
    for col in full_factor_cols:
        row = summarize_factor(full, col, col)
        if row is not None:
            row["source_group"] = "price_cross_asset"
            full_rows.append(row)
    full_rank = pd.DataFrame(full_rows).sort_values("range_lift_pct", ascending=False).reset_index(drop=True)
    full_rank.to_csv(outdir / "fullsample_factor_rank.csv", index=False)

    overlap_rows = []
    for col in full_factor_cols + overlap_extra_cols:
        row = summarize_factor(overlap, col, col)
        if row is not None:
            row["source_group"] = "calendar_geo" if col in overlap_extra_cols else "price_cross_asset"
            overlap_rows.append(row)
    overlap_rank = pd.DataFrame(overlap_rows).sort_values("range_lift_pct", ascending=False).reset_index(drop=True)
    overlap_rank.to_csv(outdir / "overlap_factor_rank.csv", index=False)

    plot_top_factors(full_rank, "XAUUSD Full Sample: Top Regime Drivers", outdir / "fullsample_top_factors.png")
    plot_top_factors(overlap_rank, "XAUUSD Overlap Sample: Top Regime Drivers", outdir / "overlap_top_factors.png")

    full_features_model = [
        "PREV_DAY_COMPRESSION",
        "OPEN_NEAR_PREV_EXTREME",
        "asia_compression_plus_europe_break",
        "DOLLAR_SHOCK",
        "YIELD_SHOCK",
        "VIX_SHOCK",
        "OIL_SHOCK",
        "DOLLAR_YIELD_CONFLUENCE",
    ]
    overlap_features_model = [
        "FED_POLICY",
        "US_INFLATION",
        "GEO_ANY_SHOCK",
        "WEEKEND_GEO_CARRY",
        "PREV_DAY_COMPRESSION",
        "OPEN_NEAR_PREV_EXTREME",
        "asia_compression_plus_europe_break",
        "DOLLAR_SHOCK",
        "YIELD_SHOCK",
        "VIX_SHOCK",
    ]

    full_model_summary, full_coef = fit_models(full, full_features_model, outdir, "fullsample")
    overlap_model_summary, overlap_coef = fit_models(overlap, overlap_features_model, outdir, "overlap")
    plot_coefficients(full_coef, "fullsample_high_vol_logit", "Full Sample High-Vol Logit Coefficients", outdir / "fullsample_highvol_coefficients.png")
    plot_coefficients(overlap_coef, "overlap_high_vol_logit", "Overlap High-Vol Logit Coefficients", outdir / "overlap_highvol_coefficients.png")

    baseline_full = full.loc[full["range_ratio"].notna()]
    baseline_overlap = overlap.loc[overlap["range_ratio"].notna()]
    lines = [
        "# XAUUSD Regime Factor Research",
        "",
        f"- MT5 sample: `{full['date'].min().date()}` to `{full['date'].max().date()}`",
        f"- Calendar+geo overlap sample: `{overlap_start.date()}` to `{overlap_end.date()}`",
        f"- Full-sample mean range ratio: `{baseline_full['range_ratio'].mean():.2f}`",
        f"- Overlap-sample mean range ratio: `{baseline_overlap['range_ratio'].mean():.2f}`",
        "",
        "## Full Sample Top Drivers",
        "",
    ]
    for _, row in full_rank.head(8).iterrows():
        lines.append(
            f"- `{row['label']}`: `{int(row['event_days'])}` days, avg range ratio `{row['avg_range_ratio']:.2f}`, "
            f"median `{row['median_range_ratio']:.2f}`, range lift `{row['range_lift_pct']:.1f}%`, "
            f"high-vol rate `{row['high_vol_rate']:.1%}`, trend-day rate `{row['trend_day_rate']:.1%}`"
        )
    lines.extend(["", "## Overlap Sample Top Drivers", ""])
    for _, row in overlap_rank.head(10).iterrows():
        lines.append(
            f"- `{row['label']}` ({row['source_group']}): `{int(row['event_days'])}` days, avg range ratio `{row['avg_range_ratio']:.2f}`, "
            f"median `{row['median_range_ratio']:.2f}`, range lift `{row['range_lift_pct']:.1f}%`, "
            f"high-vol rate `{row['high_vol_rate']:.1%}`, trend-day rate `{row['trend_day_rate']:.1%}`"
        )
    lines.extend(
        [
            "",
            "## Model Summary",
            "",
        ]
    )
    for df_name, model_summary in [("fullsample", full_model_summary), ("overlap", overlap_model_summary)]:
        for _, row in model_summary.iterrows():
            metrics = []
            if pd.notna(row.get("oos_auc", np.nan)):
                metrics.append(f"OOS AUC `{row['oos_auc']:.2f}`")
            if pd.notna(row.get("oos_corr", np.nan)):
                metrics.append(f"OOS corr `{row['oos_corr']:.2f}`")
            if pd.notna(row.get("train_pseudo_r2", np.nan)):
                metrics.append(f"train pseudo-R2 `{row['train_pseudo_r2']:.2f}`")
            if pd.notna(row.get("train_r2", np.nan)):
                metrics.append(f"train R2 `{row['train_r2']:.2f}`")
            lines.append(f"- `{row['model']}`: " + ", ".join(metrics))
    lines.extend(
        [
            "",
            "## Files",
            "",
            "- `xau_regime_full_dataset.csv`",
            "- `xau_regime_overlap_dataset.csv`",
            "- `fullsample_factor_rank.csv`",
            "- `overlap_factor_rank.csv`",
            "- `fullsample_model_summary.csv`",
            "- `overlap_model_summary.csv`",
            "- `fullsample_model_coefficients.csv`",
            "- `overlap_model_coefficients.csv`",
            "- `fullsample_top_factors.png`",
            "- `overlap_top_factors.png`",
            "- `fullsample_highvol_coefficients.png`",
            "- `overlap_highvol_coefficients.png`",
        ]
    )
    (outdir / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Saved report: {outdir / 'summary.md'}")
    print(f"Point={point} ContractSize={contract_size}")


if __name__ == "__main__":
    main()
