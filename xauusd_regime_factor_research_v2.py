from __future__ import annotations

import argparse
from pathlib import Path

import MetaTrader5 as mt5
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm

from xauusd_regime_switching_grid_backtest import fetch_rates, initialize_mt5


ROOT = Path(__file__).resolve().parent
BASE_ART = ROOT / "artifacts_xauusd_regime_factor_research"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Second-round XAUUSD regime-factor research with intensity and microstructure features.")
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--timeframe", default="M15")
    parser.add_argument("--bars", type=int, default=30000)
    parser.add_argument("--terminal-path", default=r"C:\MT5PortableCodex\terminal64.exe")
    parser.add_argument("--outdir", default="artifacts_xauusd_regime_factor_research_v2")
    return parser.parse_args()


def load_base_dataset(name: str) -> pd.DataFrame:
    path = BASE_ART / name
    return pd.read_csv(path, parse_dates=["date"])


def build_open_window_features(raw_bars: pd.DataFrame) -> pd.DataFrame:
    bars = raw_bars.copy()
    bars["date"] = bars["time"].dt.floor("D")
    bars["hour"] = bars["time"].dt.hour

    def summarize_window(label: str, hours: set[int]) -> pd.DataFrame:
        subset = bars.loc[bars["hour"].isin(hours)].copy()
        grouped = (
            subset.groupby("date", as_index=False)
            .agg(
                open=("open", "first"),
                high=("high", "max"),
                low=("low", "min"),
                close=("close", "last"),
                bar_count=("time", "size"),
            )
            .sort_values("date")
            .reset_index(drop=True)
        )
        grouped[f"{label}_range"] = grouped["high"] - grouped["low"]
        grouped[f"{label}_body_ratio"] = (grouped["close"] - grouped["open"]).abs() / grouped[f"{label}_range"].replace(0, np.nan)
        grouped[f"{label}_range_ratio"] = grouped[f"{label}_range"] / grouped[f"{label}_range"].shift(1).rolling(20, min_periods=10).median()
        grouped = grouped.rename(
            columns={
                "open": f"{label}_open",
                "high": f"{label}_high",
                "low": f"{label}_low",
                "close": f"{label}_close",
                "bar_count": f"{label}_bar_count",
            }
        )
        return grouped

    london2h = summarize_window("london2h", {8, 9})
    us2h = summarize_window("us2h", {16, 17})
    merged = london2h.merge(us2h, on="date", how="outer").sort_values("date").reset_index(drop=True)
    return merged


def add_intensity_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy().sort_values("date").reset_index(drop=True)
    for source, target in [
        ("dxy_ret", "dxy_abs_z20"),
        ("tnx_change", "tnx_abs_z20"),
        ("tip_ret", "tip_abs_z20"),
        ("vix_ret", "vix_abs_z20"),
        ("oil_ret", "oil_abs_z20"),
        ("spx_ret", "spx_abs_z20"),
    ]:
        rolling_std = out[source].shift(1).rolling(20, min_periods=10).std()
        out[target] = out[source].abs() / rolling_std.replace(0, np.nan)

    out["dollar_yield_intensity"] = out["dxy_abs_z20"] * out["tnx_abs_z20"]
    out["dollar_vix_intensity"] = out["dxy_abs_z20"] * out["vix_abs_z20"]
    out["risk_basket_intensity"] = out[["vix_abs_z20", "oil_abs_z20", "spx_abs_z20"]].mean(axis=1)
    out["open_outside_prev_range_int"] = out["OPEN_OUTSIDE_PREV_RANGE"].astype(float)
    return out


def add_london_us_break_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["london2h_break_prevday"] = (out["london2h_high"] > out["prev_day_high"]) | (out["london2h_low"] < out["prev_day_low"])
    out["london2h_break_asia"] = (out["london2h_high"] > out["high_asia"]) | (out["london2h_low"] < out["low_asia"])
    out["us2h_break_prevday"] = (out["us2h_high"] > out["prev_day_high"]) | (out["us2h_low"] < out["prev_day_low"])
    out["us2h_break_europe"] = (out["us2h_high"] > out["high_europe"]) | (out["us2h_low"] < out["low_europe"])
    return out


def build_macro_intensity(overlap: pd.DataFrame) -> pd.DataFrame:
    long_df = pd.read_csv(BASE_ART / "macro_event_days_long.csv", parse_dates=["date"])
    pivot = long_df.pivot_table(index="date", columns="macro_family", values="event_rows", aggfunc="sum", fill_value=0)
    pivot.columns = [f"{col}_rows" for col in pivot.columns]
    pivot = pivot.reset_index()
    pivot["usd_high_total_rows"] = pivot[[col for col in pivot.columns if col.startswith("US_") or col == "date"]].drop(columns=["date"], errors="ignore").sum(axis=1)
    merged = overlap.merge(pivot, on="date", how="left")
    row_cols = [col for col in merged.columns if col.endswith("_rows")]
    for col in row_cols:
        merged[col] = merged[col].fillna(0.0)
    return merged


def add_geo_intensity(overlap: pd.DataFrame) -> pd.DataFrame:
    out = overlap.copy()
    geo_score_cols = [col for col in out.columns if col.endswith("_score") and col.startswith("GEO_")]
    out["geo_total_score"] = out[geo_score_cols].sum(axis=1)
    out["geo_max_score"] = out[geo_score_cols].max(axis=1)
    for col in geo_score_cols + ["geo_total_score", "geo_max_score"]:
        rolling = out[col].shift(1).rolling(20, min_periods=10)
        mean = rolling.mean()
        std = rolling.std().replace(0, np.nan)
        out[f"{col}_z20"] = (out[col] - mean) / std
        out[f"{col}_z20_abs"] = out[f"{col}_z20"].abs()
    out["weekend_geo_score"] = out["geo_total_score"] * out["WEEKEND_GEO_CARRY"].astype(float)
    return out


def clip_extremes(frame: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    out = frame.copy()
    for col in cols:
        if col not in out.columns:
            continue
        series = out[col].astype(float)
        finite = series.replace([np.inf, -np.inf], np.nan).dropna()
        if finite.empty:
            continue
        low = float(finite.quantile(0.01))
        high = float(finite.quantile(0.99))
        out[col] = series.clip(lower=low, upper=high)
    return out


def standardize_train_test(
    train: pd.DataFrame, test: pd.DataFrame, features: list[str], bool_features: set[str]
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, tuple[float, float]]]:
    tr = train.copy()
    te = test.copy()
    params: dict[str, tuple[float, float]] = {}
    for feature in features:
        if feature in bool_features:
            tr[feature] = tr[feature].astype(float)
            te[feature] = te[feature].astype(float)
            params[feature] = (0.0, 1.0)
            continue
        mean = float(tr[feature].mean())
        std = float(tr[feature].std())
        if not np.isfinite(std) or std == 0.0:
            std = 1.0
        tr[feature] = (tr[feature] - mean) / std
        te[feature] = (te[feature] - mean) / std
        params[feature] = (mean, std)
    return tr, te, params


def standardize_full(frame: pd.DataFrame, features: list[str], bool_features: set[str], params: dict[str, tuple[float, float]]) -> pd.DataFrame:
    out = frame.copy()
    for feature in features:
        if feature in bool_features:
            out[feature] = out[feature].astype(float)
            continue
        mean, std = params[feature]
        out[feature] = (out[feature] - mean) / std
    return out


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
    return float((pos["rank"].sum() - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))


def fit_suite(
    frame: pd.DataFrame,
    features: list[str],
    bool_features: set[str],
    prefix: str,
    outdir: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = frame.loc[frame[features + ["high_vol_day", "trend_day", "regime_score"]].notna().all(axis=1)].copy()
    split_idx = max(20, int(len(df) * 0.70))
    train = df.iloc[:split_idx].copy()
    test = df.iloc[split_idx:].copy()

    train, test, params = standardize_train_test(train, test, features, bool_features)
    full_std = standardize_full(df.copy(), features, bool_features, params)

    Xtr = sm.add_constant(train[features].astype(float), has_constant="add")
    Xte = sm.add_constant(test[features].astype(float), has_constant="add")
    Xfull = sm.add_constant(full_std[features].astype(float), has_constant="add")

    high_model = sm.GLM(train["high_vol_day"].astype(float), Xtr, family=sm.families.Binomial()).fit()
    trend_model = sm.GLM(train["trend_day"].astype(float), Xtr, family=sm.families.Binomial()).fit()
    regime_model = sm.OLS(train["regime_score"].astype(float), Xtr).fit(cov_type="HC1")

    high_pred = high_model.predict(Xte) if not test.empty else pd.Series(dtype=float)
    trend_pred = trend_model.predict(Xte) if not test.empty else pd.Series(dtype=float)
    regime_pred = regime_model.predict(Xte) if not test.empty else pd.Series(dtype=float)

    summary_rows = [
        {
            "model": f"{prefix}_high_vol_logit_v2",
            "train_obs": len(train),
            "test_obs": len(test),
            "oos_auc": roc_auc_score_manual(test["high_vol_day"], high_pred) if not test.empty else np.nan,
            "train_pseudo_r2": 1.0 - high_model.deviance / high_model.null_deviance if high_model.null_deviance else np.nan,
        },
        {
            "model": f"{prefix}_trend_day_logit_v2",
            "train_obs": len(train),
            "test_obs": len(test),
            "oos_auc": roc_auc_score_manual(test["trend_day"], trend_pred) if not test.empty else np.nan,
            "train_pseudo_r2": 1.0 - trend_model.deviance / trend_model.null_deviance if trend_model.null_deviance else np.nan,
        },
        {
            "model": f"{prefix}_regime_score_ols_v2",
            "train_obs": len(train),
            "test_obs": len(test),
            "oos_corr": float(pd.Series(regime_pred).corr(test["regime_score"])) if not test.empty else np.nan,
            "train_r2": float(regime_model.rsquared),
        },
    ]

    coef_rows = []
    for model_name, model in [
        (f"{prefix}_high_vol_logit_v2", sm.GLM(full_std["high_vol_day"].astype(float), Xfull, family=sm.families.Binomial()).fit()),
        (f"{prefix}_trend_day_logit_v2", sm.GLM(full_std["trend_day"].astype(float), Xfull, family=sm.families.Binomial()).fit()),
        (f"{prefix}_regime_score_ols_v2", sm.OLS(full_std["regime_score"].astype(float), Xfull).fit(cov_type="HC1")),
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
    summary_df.to_csv(outdir / f"{prefix}_model_summary_v2.csv", index=False)
    coef_df.to_csv(outdir / f"{prefix}_model_coefficients_v2.csv", index=False)
    return summary_df, coef_df


def plot_metric_comparison(comp: pd.DataFrame, metric: str, title: str, outpath: Path) -> None:
    if comp.empty:
        return
    plot_df = comp.copy()
    fig, ax = plt.subplots(figsize=(8.6, 4.8))
    x = np.arange(len(plot_df))
    width = 0.36
    ax.bar(x - width / 2, plot_df[f"{metric}_v1"], width=width, label="v1", color="#b45309")
    ax.bar(x + width / 2, plot_df[f"{metric}_v2"], width=width, label="v2", color="#0f766e")
    ax.set_xticks(x)
    ax.set_xticklabels(plot_df["label"])
    ax.set_title(title)
    ax.grid(axis="y", alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(outpath, dpi=160)
    plt.close(fig)


def main() -> None:
    args = parse_args()
    outdir = ROOT / args.outdir
    outdir.mkdir(parents=True, exist_ok=True)

    full = load_base_dataset("xau_regime_full_dataset.csv")
    overlap = load_base_dataset("xau_regime_overlap_dataset.csv")

    initialize_mt5(args.terminal_path)
    try:
        raw_bars, point, contract_size = fetch_rates(args.symbol, args.timeframe, args.bars)
    finally:
        mt5.shutdown()

    windows = build_open_window_features(raw_bars)
    full = full.merge(windows, on="date", how="left")
    overlap = overlap.merge(windows, on="date", how="left")

    full = add_london_us_break_flags(add_intensity_features(full))
    overlap = add_london_us_break_flags(add_intensity_features(overlap))
    overlap = build_macro_intensity(overlap)
    overlap = add_geo_intensity(overlap)

    lag_cols = [
        "dxy_abs_z20",
        "tnx_abs_z20",
        "vix_abs_z20",
        "oil_abs_z20",
        "spx_abs_z20",
        "geo_total_score_z20_abs",
        "GEO_MIDDLE_EAST_score_z20_abs",
    ]
    for frame in [full, overlap]:
        for col in lag_cols:
            if col in frame.columns:
                frame[f"{col}_lag1"] = frame[col].shift(1)

    full_continuous = [
        "prev_day_range_ratio",
        "prev3_range_ratio",
        "min_prev_extreme_dist_norm",
        "range_ratio_europe",
        "range_ratio_us",
        "body_ratio_europe",
        "body_ratio_us",
        "london2h_range_ratio",
        "london2h_body_ratio",
        "us2h_range_ratio",
        "us2h_body_ratio",
        "dxy_abs_z20",
        "tnx_abs_z20",
        "vix_abs_z20",
        "oil_abs_z20",
        "spx_abs_z20",
        "dollar_yield_intensity",
        "dollar_vix_intensity",
        "risk_basket_intensity",
    ]
    overlap_continuous = full_continuous + [
        "FED_POLICY_rows",
        "US_INFLATION_rows",
        "US_LABOR_MAJOR_rows",
        "usd_high_total_rows",
        "geo_total_score_z20_abs",
        "geo_max_score_z20_abs",
        "GEO_MIDDLE_EAST_score_z20_abs",
        "weekend_geo_score",
    ]
    full = clip_extremes(full, full_continuous)
    overlap = clip_extremes(overlap, overlap_continuous)

    full_features_v2 = [
        "prev_day_range_ratio",
        "min_prev_extreme_dist_norm",
        "OPEN_OUTSIDE_PREV_RANGE",
        "range_ratio_europe",
        "body_ratio_europe",
        "london2h_range_ratio",
        "london2h_break_prevday",
        "us2h_range_ratio",
        "dxy_abs_z20",
        "tnx_abs_z20",
        "vix_abs_z20",
        "oil_abs_z20",
        "dollar_yield_intensity",
        "dollar_vix_intensity",
    ]
    full_bool_v2 = {"OPEN_OUTSIDE_PREV_RANGE", "london2h_break_prevday"}

    overlap_features_v2 = [
        "FED_POLICY_rows",
        "US_INFLATION_rows",
        "usd_high_total_rows",
        "geo_total_score_z20_abs",
        "GEO_MIDDLE_EAST_score_z20_abs",
        "WEEKEND_GEO_CARRY",
        "prev_day_range_ratio",
        "OPEN_OUTSIDE_PREV_RANGE",
        "range_ratio_europe",
        "london2h_range_ratio",
        "london2h_break_prevday",
        "dxy_abs_z20",
        "vix_abs_z20",
        "dollar_vix_intensity",
    ]
    overlap_bool_v2 = {"WEEKEND_GEO_CARRY", "OPEN_OUTSIDE_PREV_RANGE", "london2h_break_prevday"}

    full_summary_v2, full_coef_v2 = fit_suite(full, full_features_v2, full_bool_v2, "fullsample", outdir)
    overlap_summary_v2, overlap_coef_v2 = fit_suite(overlap, overlap_features_v2, overlap_bool_v2, "overlap", outdir)

    full_features_early = [
        "prev_day_range_ratio",
        "min_prev_extreme_dist_norm",
        "OPEN_OUTSIDE_PREV_RANGE",
        "london2h_range_ratio",
        "london2h_break_prevday",
        "dxy_abs_z20_lag1",
        "tnx_abs_z20_lag1",
        "vix_abs_z20_lag1",
        "oil_abs_z20_lag1",
    ]
    full_bool_early = {"OPEN_OUTSIDE_PREV_RANGE", "london2h_break_prevday"}
    overlap_features_early = [
        "WEEKEND_GEO_CARRY",
        "prev_day_range_ratio",
        "OPEN_OUTSIDE_PREV_RANGE",
        "london2h_range_ratio",
        "london2h_break_prevday",
        "dxy_abs_z20_lag1",
        "vix_abs_z20_lag1",
        "geo_total_score_z20_abs_lag1",
    ]
    overlap_bool_early = {"WEEKEND_GEO_CARRY", "OPEN_OUTSIDE_PREV_RANGE", "london2h_break_prevday"}
    full_summary_early, _ = fit_suite(full, full_features_early, full_bool_early, "fullsample_early", outdir)
    overlap_summary_early, _ = fit_suite(overlap, overlap_features_early, overlap_bool_early, "overlap_early", outdir)

    full_summary_v1 = pd.read_csv(BASE_ART / "fullsample_model_summary.csv")
    overlap_summary_v1 = pd.read_csv(BASE_ART / "overlap_model_summary.csv")

    compare_rows = [
        {
            "label": "full_high_vol_auc",
            "metric": "auc",
            "metric_v1": float(full_summary_v1.loc[full_summary_v1["model"] == "fullsample_high_vol_logit", "oos_auc"].iloc[0]),
            "metric_v2": float(full_summary_v2.loc[full_summary_v2["model"] == "fullsample_high_vol_logit_v2", "oos_auc"].iloc[0]),
        },
        {
            "label": "full_trend_auc",
            "metric": "auc",
            "metric_v1": float(full_summary_v1.loc[full_summary_v1["model"] == "fullsample_trend_day_logit", "oos_auc"].iloc[0]),
            "metric_v2": float(full_summary_v2.loc[full_summary_v2["model"] == "fullsample_trend_day_logit_v2", "oos_auc"].iloc[0]),
        },
        {
            "label": "full_regime_corr",
            "metric": "corr",
            "metric_v1": float(full_summary_v1.loc[full_summary_v1["model"] == "fullsample_regime_score_ols", "oos_corr"].iloc[0]),
            "metric_v2": float(full_summary_v2.loc[full_summary_v2["model"] == "fullsample_regime_score_ols_v2", "oos_corr"].iloc[0]),
        },
        {
            "label": "overlap_high_vol_auc",
            "metric": "auc",
            "metric_v1": float(overlap_summary_v1.loc[overlap_summary_v1["model"] == "overlap_high_vol_logit", "oos_auc"].iloc[0]),
            "metric_v2": float(overlap_summary_v2.loc[overlap_summary_v2["model"] == "overlap_high_vol_logit_v2", "oos_auc"].iloc[0]),
        },
        {
            "label": "overlap_trend_auc",
            "metric": "auc",
            "metric_v1": float(overlap_summary_v1.loc[overlap_summary_v1["model"] == "overlap_trend_day_logit", "oos_auc"].iloc[0]),
            "metric_v2": float(overlap_summary_v2.loc[overlap_summary_v2["model"] == "overlap_trend_day_logit_v2", "oos_auc"].iloc[0]),
        },
        {
            "label": "overlap_regime_corr",
            "metric": "corr",
            "metric_v1": float(overlap_summary_v1.loc[overlap_summary_v1["model"] == "overlap_regime_score_ols", "oos_corr"].iloc[0]),
            "metric_v2": float(overlap_summary_v2.loc[overlap_summary_v2["model"] == "overlap_regime_score_ols_v2", "oos_corr"].iloc[0]),
        },
    ]
    comparison = pd.DataFrame(compare_rows)
    comparison.to_csv(outdir / "v1_vs_v2_model_comparison.csv", index=False)

    early_rows = [
        {
            "label": "full_early_high_vol_auc",
            "metric": "auc",
            "metric_v2_early": float(full_summary_early.loc[full_summary_early["model"] == "fullsample_early_high_vol_logit_v2", "oos_auc"].iloc[0]),
        },
        {
            "label": "full_early_regime_corr",
            "metric": "corr",
            "metric_v2_early": float(full_summary_early.loc[full_summary_early["model"] == "fullsample_early_regime_score_ols_v2", "oos_corr"].iloc[0]),
        },
        {
            "label": "overlap_early_high_vol_auc",
            "metric": "auc",
            "metric_v2_early": float(overlap_summary_early.loc[overlap_summary_early["model"] == "overlap_early_high_vol_logit_v2", "oos_auc"].iloc[0]),
        },
        {
            "label": "overlap_early_regime_corr",
            "metric": "corr",
            "metric_v2_early": float(overlap_summary_early.loc[overlap_summary_early["model"] == "overlap_early_regime_score_ols_v2", "oos_corr"].iloc[0]),
        },
    ]
    early_comparison = pd.DataFrame(early_rows)
    early_comparison.to_csv(outdir / "v2_early_model_comparison.csv", index=False)

    plot_metric_comparison(
        comparison.loc[comparison["metric"] == "auc"].rename(columns={"metric_v1": "auc_v1", "metric_v2": "auc_v2"}),
        "auc",
        "XAUUSD Regime Models: v1 vs v2 AUC",
        outdir / "v1_vs_v2_auc.png",
    )
    plot_metric_comparison(
        comparison.loc[comparison["metric"] == "corr"].rename(columns={"metric_v1": "corr_v1", "metric_v2": "corr_v2"}),
        "corr",
        "XAUUSD Regime Models: v1 vs v2 OOS Correlation",
        outdir / "v1_vs_v2_corr.png",
    )

    full.to_csv(outdir / "xau_regime_full_dataset_v2.csv", index=False)
    overlap.to_csv(outdir / "xau_regime_overlap_dataset_v2.csv", index=False)

    top_full = full_coef_v2.loc[(full_coef_v2["model"] == "fullsample_high_vol_logit_v2") & (full_coef_v2["feature"] != "const")].copy()
    top_full = top_full.sort_values("coef", ascending=False)
    top_overlap = overlap_coef_v2.loc[(overlap_coef_v2["model"] == "overlap_high_vol_logit_v2") & (overlap_coef_v2["feature"] != "const")].copy()
    top_overlap = top_overlap.sort_values("coef", ascending=False)

    lines = [
        "# XAUUSD Regime Factor Research v2",
        "",
        "This round adds intensity variables, London/New York first-two-hour microstructure, and interaction terms on top of the original v1 factor stack.",
        "",
        "## v1 vs v2",
        "",
    ]
    for _, row in comparison.iterrows():
        lines.append(
            f"- `{row['label']}`: v1 `{row['metric_v1']:.3f}` -> v2 `{row['metric_v2']:.3f}` (delta `{row['metric_v2'] - row['metric_v1']:+.3f}`)"
        )
    lines.extend(["", "## Top v2 High-Vol Drivers", ""])
    for _, row in top_full.head(8).iterrows():
        lines.append(f"- `fullsample {row['feature']}`: coef `{row['coef']:.3f}`, p-value `{row['pvalue']:.3f}`")
    for _, row in top_overlap.head(8).iterrows():
        lines.append(f"- `overlap {row['feature']}`: coef `{row['coef']:.3f}`, p-value `{row['pvalue']:.3f}`")
    lines.extend(["", "## Early-Observable Sanity Check", ""])
    for _, row in early_comparison.iterrows():
        lines.append(f"- `{row['label']}`: `{row['metric_v2_early']:.3f}`")
    lines.extend(
        [
            "",
            "## Files",
            "",
            "- `xau_regime_full_dataset_v2.csv`",
            "- `xau_regime_overlap_dataset_v2.csv`",
            "- `fullsample_model_summary_v2.csv`",
            "- `overlap_model_summary_v2.csv`",
            "- `fullsample_model_coefficients_v2.csv`",
            "- `overlap_model_coefficients_v2.csv`",
            "- `v1_vs_v2_model_comparison.csv`",
            "- `v2_early_model_comparison.csv`",
            "- `v1_vs_v2_auc.png`",
            "- `v1_vs_v2_corr.png`",
        ]
    )
    (outdir / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Saved report: {outdir / 'summary.md'}")
    print(f"Point={point} ContractSize={contract_size}")


if __name__ == "__main__":
    main()
