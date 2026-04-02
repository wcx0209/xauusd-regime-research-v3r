from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm


ROOT = Path(__file__).resolve().parent
V2_ART = ROOT / "artifacts_xauusd_regime_factor_research_v2"

YAHOO_HEADERS = {"User-Agent": "Mozilla/5.0"}
PROXY_SERIES = {
    "gld": "GLD",
    "gc": "GC=F",
    "gdx": "GDX",
    "si": "SI=F",
    "gvz": "^GVZ",
    "hyg": "HYG",
    "tlt": "TLT",
    "jpy": "JPY=X",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Third-round XAUUSD regime-factor research with external proxy factors.")
    parser.add_argument("--outdir", default="artifacts_xauusd_regime_factor_research_v3")
    parser.add_argument("--max-additions-full", type=int, default=3)
    parser.add_argument("--max-additions-overlap", type=int, default=2)
    return parser.parse_args()


def load_v2_dataset(name: str) -> pd.DataFrame:
    return pd.read_csv(V2_ART / name, parse_dates=["date"])


def fetch_yahoo_chart(symbol: str, cache_dir: Path) -> pd.DataFrame:
    cache_path = cache_dir / f"{symbol.replace('^', 'idx_').replace('=', '_')}.json"
    if cache_path.exists():
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    else:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol)}?range=3y&interval=1d"
        request = Request(url, headers=YAHOO_HEADERS)
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        cache_path.write_text(json.dumps(payload), encoding="utf-8")

    result = payload["chart"]["result"][0]
    quote_data = result["indicators"]["quote"][0]
    frame = pd.DataFrame(
        {
            "timestamp": result.get("timestamp", []),
            "close": quote_data.get("close", []),
            "volume": quote_data.get("volume", []),
        }
    )
    frame = frame.dropna(subset=["timestamp", "close"]).copy()
    frame["date"] = pd.to_datetime(frame["timestamp"], unit="s").dt.floor("D")
    return frame[["date", "close", "volume"]].drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)


def rolling_abs_zscore(series: pd.Series, window: int = 20) -> pd.Series:
    std = series.shift(1).rolling(window, min_periods=10).std()
    return series.abs() / std.replace(0, np.nan)


def rolling_ratio(series: pd.Series, window: int = 20) -> pd.Series:
    median = series.shift(1).rolling(window, min_periods=10).median()
    return series / median.replace(0, np.nan)


def build_proxy_features(start_date: pd.Timestamp, end_date: pd.Timestamp, outdir: Path) -> pd.DataFrame:
    cache_dir = outdir / "yahoo_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    merged: pd.DataFrame | None = None

    for key, symbol in PROXY_SERIES.items():
        series = fetch_yahoo_chart(symbol, cache_dir)
        series = series.rename(columns={"close": f"{key}_close", "volume": f"{key}_volume"})
        merged = series if merged is None else merged.merge(series, on="date", how="outer")

    assert merged is not None
    merged = merged.sort_values("date").reset_index(drop=True)
    merged = merged.loc[(merged["date"] >= start_date - pd.Timedelta(days=40)) & (merged["date"] <= end_date)].copy()
    merged = merged.ffill()

    for key in PROXY_SERIES:
        close_col = f"{key}_close"
        vol_col = f"{key}_volume"
        merged[f"{key}_ret"] = merged[close_col].pct_change()
        merged[f"{key}_abs_z20"] = rolling_abs_zscore(merged[f"{key}_ret"])
        merged[f"{key}_volume_ratio20"] = rolling_ratio(merged[vol_col].replace(0, np.nan))
        merged[f"{key}_volume_z20"] = (
            (merged[vol_col] - merged[vol_col].shift(1).rolling(20, min_periods=10).mean())
            / merged[vol_col].shift(1).rolling(20, min_periods=10).std().replace(0, np.nan)
        )

    merged["gld_flow_proxy"] = merged["gld_abs_z20"] * merged["gld_volume_ratio20"]
    merged["gc_flow_proxy"] = merged["gc_abs_z20"] * merged["gc_volume_ratio20"]
    merged["miners_vs_credit"] = merged["gdx_ret"] - merged["hyg_ret"]
    merged["rates_vs_credit"] = merged["tlt_ret"] - merged["hyg_ret"]
    merged["gold_vol_credit_intensity"] = merged["gvz_abs_z20"] * merged["hyg_abs_z20"]
    merged["safe_haven_rotation"] = merged["jpy_abs_z20"] + merged["tlt_abs_z20"]
    return merged


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
    train: pd.DataFrame,
    test: pd.DataFrame,
    features: list[str],
    bool_features: set[str],
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


def standardize_full(
    frame: pd.DataFrame,
    features: list[str],
    bool_features: set[str],
    params: dict[str, tuple[float, float]],
) -> pd.DataFrame:
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


def fit_models(train: pd.DataFrame, test: pd.DataFrame, features: list[str], bool_features: set[str]) -> dict[str, float]:
    train_std, test_std, params = standardize_train_test(train, test, features, bool_features)
    Xtr = sm.add_constant(train_std[features].astype(float), has_constant="add")
    Xte = sm.add_constant(test_std[features].astype(float), has_constant="add")
    try:
        high_model = sm.GLM(train_std["high_vol_day"].astype(float), Xtr, family=sm.families.Binomial()).fit()
        trend_model = sm.GLM(train_std["trend_day"].astype(float), Xtr, family=sm.families.Binomial()).fit()
        regime_model = sm.OLS(train_std["regime_score"].astype(float), Xtr).fit(cov_type="HC1")
    except Exception:
        return {
            "high_auc": float("nan"),
            "trend_auc": float("nan"),
            "regime_corr": float("nan"),
            "train_high_pseudo_r2": float("nan"),
            "train_trend_pseudo_r2": float("nan"),
            "train_regime_r2": float("nan"),
        }

    high_pred = high_model.predict(Xte)
    trend_pred = trend_model.predict(Xte)
    regime_pred = regime_model.predict(Xte)
    return {
        "high_auc": roc_auc_score_manual(test_std["high_vol_day"], high_pred),
        "trend_auc": roc_auc_score_manual(test_std["trend_day"], trend_pred),
        "regime_corr": float(pd.Series(regime_pred).corr(test_std["regime_score"])),
        "train_high_pseudo_r2": 1.0 - high_model.deviance / high_model.null_deviance if high_model.null_deviance else np.nan,
        "train_trend_pseudo_r2": 1.0 - trend_model.deviance / trend_model.null_deviance if trend_model.null_deviance else np.nan,
        "train_regime_r2": float(regime_model.rsquared),
    }


def fit_full_coefs(frame: pd.DataFrame, features: list[str], bool_features: set[str], prefix: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = frame.loc[frame[features + ["high_vol_day", "trend_day", "regime_score"]].notna().all(axis=1)].copy()
    split_idx = max(20, int(len(df) * 0.70))
    train = df.iloc[:split_idx].copy()
    test = df.iloc[split_idx:].copy()
    train_std, test_std, params = standardize_train_test(train, test, features, bool_features)
    full_std = standardize_full(df.copy(), features, bool_features, params)
    Xfull = sm.add_constant(full_std[features].astype(float), has_constant="add")

    high_model = sm.GLM(full_std["high_vol_day"].astype(float), Xfull, family=sm.families.Binomial()).fit()
    trend_model = sm.GLM(full_std["trend_day"].astype(float), Xfull, family=sm.families.Binomial()).fit()
    regime_model = sm.OLS(full_std["regime_score"].astype(float), Xfull).fit(cov_type="HC1")

    test_metrics = fit_models(train, test, features, bool_features)
    summary = pd.DataFrame(
        [
            {
                "model": f"{prefix}_high_vol_logit_v3",
                "train_obs": len(train),
                "test_obs": len(test),
                "oos_auc": test_metrics["high_auc"],
                "train_pseudo_r2": test_metrics["train_high_pseudo_r2"],
            },
            {
                "model": f"{prefix}_trend_day_logit_v3",
                "train_obs": len(train),
                "test_obs": len(test),
                "oos_auc": test_metrics["trend_auc"],
                "train_pseudo_r2": test_metrics["train_trend_pseudo_r2"],
            },
            {
                "model": f"{prefix}_regime_score_ols_v3",
                "train_obs": len(train),
                "test_obs": len(test),
                "oos_corr": test_metrics["regime_corr"],
                "train_r2": test_metrics["train_regime_r2"],
            },
        ]
    )

    coef_rows = []
    for model_name, model in [
        (f"{prefix}_high_vol_logit_v3", high_model),
        (f"{prefix}_trend_day_logit_v3", trend_model),
        (f"{prefix}_regime_score_ols_v3", regime_model),
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
    return summary, pd.DataFrame(coef_rows)


def composite_score(metrics: dict[str, float]) -> float:
    parts = [
        metrics["high_auc"],
        metrics["trend_auc"],
        max(metrics["regime_corr"], 0.0) if np.isfinite(metrics["regime_corr"]) else np.nan,
    ]
    valid = [value for value in parts if np.isfinite(value)]
    if not valid:
        return float("-inf")
    return float(np.average(valid, weights=[0.4, 0.2, 0.4][: len(valid)]))


def forward_select(
    frame: pd.DataFrame,
    base_features: list[str],
    bool_features: set[str],
    candidates: list[str],
    max_additions: int,
) -> list[str]:
    df = frame.loc[frame[base_features + candidates + ["high_vol_day", "trend_day", "regime_score"]].notna().all(axis=1)].copy()
    split_idx = max(20, int(len(df) * 0.70))
    train = df.iloc[:split_idx].copy()
    inner_split = max(15, int(len(train) * 0.70))
    subtrain = train.iloc[:inner_split].copy()
    val = train.iloc[inner_split:].copy()

    selected = list(base_features)
    remaining = [col for col in candidates if col not in selected]
    current_best = composite_score(fit_models(subtrain, val, selected, bool_features))

    for _ in range(max_additions):
        best_feature = None
        best_score = current_best
        for feature in remaining:
            metrics = fit_models(subtrain, val, selected + [feature], bool_features)
            score = composite_score(metrics)
            if score > best_score + 0.003:
                best_feature = feature
                best_score = score
        if best_feature is None:
            break
        selected.append(best_feature)
        remaining.remove(best_feature)
        current_best = best_score
    return selected


def plot_v2_v3(metric_rows: pd.DataFrame, metric: str, title: str, outpath: Path) -> None:
    fig, ax = plt.subplots(figsize=(8.4, 4.8))
    x = np.arange(len(metric_rows))
    width = 0.36
    ax.bar(x - width / 2, metric_rows[f"{metric}_v2"], width=width, color="#0f766e", label="v2")
    ax.bar(x + width / 2, metric_rows[f"{metric}_v3"], width=width, color="#1d4ed8", label="v3")
    ax.set_xticks(x)
    ax.set_xticklabels(metric_rows["label"])
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

    full = load_v2_dataset("xau_regime_full_dataset_v2.csv")
    overlap = load_v2_dataset("xau_regime_overlap_dataset_v2.csv")

    start_date = min(full["date"].min(), overlap["date"].min())
    end_date = max(full["date"].max(), overlap["date"].max())
    proxies = build_proxy_features(start_date, end_date, outdir)

    full = full.merge(proxies, on="date", how="left")
    overlap = overlap.merge(proxies, on="date", how="left")

    proxy_features = [
        "gld_abs_z20",
        "gld_volume_ratio20",
        "gld_volume_z20",
        "gld_flow_proxy",
        "gc_abs_z20",
        "gc_volume_ratio20",
        "gc_volume_z20",
        "gc_flow_proxy",
        "gdx_ret",
        "si_ret",
        "gvz_abs_z20",
        "hyg_ret",
        "tlt_ret",
        "jpy_ret",
        "miners_vs_credit",
        "rates_vs_credit",
        "gold_vol_credit_intensity",
        "safe_haven_rotation",
    ]
    full = clip_extremes(full, proxy_features)
    overlap = clip_extremes(overlap, proxy_features)

    laggable = proxy_features.copy()
    for frame in [full, overlap]:
        for col in laggable:
            frame[f"{col}_lag1"] = frame[col].shift(1)

    full_base_v2 = [
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
    full_bool = {"OPEN_OUTSIDE_PREV_RANGE", "london2h_break_prevday"}
    overlap_base_v2 = [
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
    overlap_bool = {"WEEKEND_GEO_CARRY", "OPEN_OUTSIDE_PREV_RANGE", "london2h_break_prevday"}

    full_early_v2 = [
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
    overlap_early_v2 = [
        "WEEKEND_GEO_CARRY",
        "prev_day_range_ratio",
        "OPEN_OUTSIDE_PREV_RANGE",
        "london2h_range_ratio",
        "london2h_break_prevday",
        "dxy_abs_z20_lag1",
        "vix_abs_z20_lag1",
        "geo_total_score_z20_abs_lag1",
    ]

    full_candidates = proxy_features
    overlap_candidates = proxy_features
    full_early_candidates = [f"{col}_lag1" for col in proxy_features]
    overlap_early_candidates = [f"{col}_lag1" for col in proxy_features]

    full_features_v3 = forward_select(full, full_base_v2, full_bool, full_candidates, args.max_additions_full)
    overlap_features_v3 = forward_select(overlap, overlap_base_v2, overlap_bool, overlap_candidates, args.max_additions_overlap)
    full_early_features_v3 = forward_select(full, full_early_v2, full_bool, full_early_candidates, args.max_additions_full)
    overlap_early_features_v3 = forward_select(overlap, overlap_early_v2, overlap_bool, overlap_early_candidates, args.max_additions_overlap)

    full_summary_v3, full_coef_v3 = fit_full_coefs(full, full_features_v3, full_bool, "fullsample")
    overlap_summary_v3, overlap_coef_v3 = fit_full_coefs(overlap, overlap_features_v3, overlap_bool, "overlap")
    full_early_summary_v3, full_early_coef_v3 = fit_full_coefs(full, full_early_features_v3, full_bool, "fullsample_early")
    overlap_early_summary_v3, overlap_early_coef_v3 = fit_full_coefs(overlap, overlap_early_features_v3, overlap_bool, "overlap_early")

    full_summary_v2 = pd.read_csv(V2_ART / "fullsample_model_summary_v2.csv")
    overlap_summary_v2 = pd.read_csv(V2_ART / "overlap_model_summary_v2.csv")
    early_v2 = pd.read_csv(V2_ART / "v2_early_model_comparison.csv")

    comparison = pd.DataFrame(
        [
            {
                "label": "full_high_vol_auc",
                "metric": "auc",
                "metric_v2": float(full_summary_v2.loc[full_summary_v2["model"] == "fullsample_high_vol_logit_v2", "oos_auc"].iloc[0]),
                "metric_v3": float(full_summary_v3.loc[full_summary_v3["model"] == "fullsample_high_vol_logit_v3", "oos_auc"].iloc[0]),
            },
            {
                "label": "full_trend_auc",
                "metric": "auc",
                "metric_v2": float(full_summary_v2.loc[full_summary_v2["model"] == "fullsample_trend_day_logit_v2", "oos_auc"].iloc[0]),
                "metric_v3": float(full_summary_v3.loc[full_summary_v3["model"] == "fullsample_trend_day_logit_v3", "oos_auc"].iloc[0]),
            },
            {
                "label": "full_regime_corr",
                "metric": "corr",
                "metric_v2": float(full_summary_v2.loc[full_summary_v2["model"] == "fullsample_regime_score_ols_v2", "oos_corr"].iloc[0]),
                "metric_v3": float(full_summary_v3.loc[full_summary_v3["model"] == "fullsample_regime_score_ols_v3", "oos_corr"].iloc[0]),
            },
            {
                "label": "overlap_high_vol_auc",
                "metric": "auc",
                "metric_v2": float(overlap_summary_v2.loc[overlap_summary_v2["model"] == "overlap_high_vol_logit_v2", "oos_auc"].iloc[0]),
                "metric_v3": float(overlap_summary_v3.loc[overlap_summary_v3["model"] == "overlap_high_vol_logit_v3", "oos_auc"].iloc[0]),
            },
            {
                "label": "overlap_trend_auc",
                "metric": "auc",
                "metric_v2": float(overlap_summary_v2.loc[overlap_summary_v2["model"] == "overlap_trend_day_logit_v2", "oos_auc"].iloc[0]),
                "metric_v3": float(overlap_summary_v3.loc[overlap_summary_v3["model"] == "overlap_trend_day_logit_v3", "oos_auc"].iloc[0]),
            },
            {
                "label": "overlap_regime_corr",
                "metric": "corr",
                "metric_v2": float(overlap_summary_v2.loc[overlap_summary_v2["model"] == "overlap_regime_score_ols_v2", "oos_corr"].iloc[0]),
                "metric_v3": float(overlap_summary_v3.loc[overlap_summary_v3["model"] == "overlap_regime_score_ols_v3", "oos_corr"].iloc[0]),
            },
        ]
    )
    comparison.to_csv(outdir / "v2_vs_v3_model_comparison.csv", index=False)

    early_comparison = pd.DataFrame(
        [
            {
                "label": "full_early_high_vol_auc",
                "metric": "auc",
                "metric_v2": float(early_v2.loc[early_v2["label"] == "full_early_high_vol_auc", "metric_v2_early"].iloc[0]),
                "metric_v3": float(full_early_summary_v3.loc[full_early_summary_v3["model"] == "fullsample_early_high_vol_logit_v3", "oos_auc"].iloc[0]),
            },
            {
                "label": "full_early_regime_corr",
                "metric": "corr",
                "metric_v2": float(early_v2.loc[early_v2["label"] == "full_early_regime_corr", "metric_v2_early"].iloc[0]),
                "metric_v3": float(full_early_summary_v3.loc[full_early_summary_v3["model"] == "fullsample_early_regime_score_ols_v3", "oos_corr"].iloc[0]),
            },
            {
                "label": "overlap_early_high_vol_auc",
                "metric": "auc",
                "metric_v2": float(early_v2.loc[early_v2["label"] == "overlap_early_high_vol_auc", "metric_v2_early"].iloc[0]),
                "metric_v3": float(overlap_early_summary_v3.loc[overlap_early_summary_v3["model"] == "overlap_early_high_vol_logit_v3", "oos_auc"].iloc[0]),
            },
            {
                "label": "overlap_early_regime_corr",
                "metric": "corr",
                "metric_v2": float(early_v2.loc[early_v2["label"] == "overlap_early_regime_corr", "metric_v2_early"].iloc[0]),
                "metric_v3": float(overlap_early_summary_v3.loc[overlap_early_summary_v3["model"] == "overlap_early_regime_score_ols_v3", "oos_corr"].iloc[0]),
            },
        ]
    )
    early_comparison.to_csv(outdir / "v2_vs_v3_early_model_comparison.csv", index=False)

    plot_v2_v3(
        comparison.loc[comparison["metric"] == "auc"].rename(columns={"metric_v2": "auc_v2", "metric_v3": "auc_v3"}),
        "auc",
        "XAUUSD Regime Models: v2 vs v3 AUC",
        outdir / "v2_vs_v3_auc.png",
    )
    plot_v2_v3(
        pd.concat(
            [
                comparison.loc[comparison["metric"] == "corr", ["label", "metric_v2", "metric_v3"]],
                early_comparison.loc[early_comparison["metric"] == "corr", ["label", "metric_v2", "metric_v3"]],
            ],
            ignore_index=True,
        ).rename(columns={"metric_v2": "corr_v2", "metric_v3": "corr_v3"}),
        "corr",
        "XAUUSD Regime Models: v2 vs v3 OOS Correlation",
        outdir / "v2_vs_v3_corr.png",
    )

    selection_rows = [
        {"model_group": "full_explain", "selected_features": ",".join(full_features_v3)},
        {"model_group": "overlap_explain", "selected_features": ",".join(overlap_features_v3)},
        {"model_group": "full_early", "selected_features": ",".join(full_early_features_v3)},
        {"model_group": "overlap_early", "selected_features": ",".join(overlap_early_features_v3)},
    ]
    pd.DataFrame(selection_rows).to_csv(outdir / "selected_features_v3.csv", index=False)

    full_summary_v3.to_csv(outdir / "fullsample_model_summary_v3.csv", index=False)
    overlap_summary_v3.to_csv(outdir / "overlap_model_summary_v3.csv", index=False)
    full_early_summary_v3.to_csv(outdir / "fullsample_early_model_summary_v3.csv", index=False)
    overlap_early_summary_v3.to_csv(outdir / "overlap_early_model_summary_v3.csv", index=False)
    full_coef_v3.to_csv(outdir / "fullsample_model_coefficients_v3.csv", index=False)
    overlap_coef_v3.to_csv(outdir / "overlap_model_coefficients_v3.csv", index=False)
    full_early_coef_v3.to_csv(outdir / "fullsample_early_model_coefficients_v3.csv", index=False)
    overlap_early_coef_v3.to_csv(outdir / "overlap_early_model_coefficients_v3.csv", index=False)
    full.to_csv(outdir / "xau_regime_full_dataset_v3.csv", index=False)
    overlap.to_csv(outdir / "xau_regime_overlap_dataset_v3.csv", index=False)

    lines = [
        "# XAUUSD Regime Factor Research v3",
        "",
        "This round keeps the v2 stack and adds external open-source proxies for ETF flow, COMEX activity, gold volatility, miners, credit, rates, and safe-haven FX.",
        "",
        "## Selected External Additions",
        "",
    ]
    for row in selection_rows:
        lines.append(f"- `{row['model_group']}`: `{row['selected_features']}`")
    lines.extend(["", "## v2 vs v3", ""])
    for _, row in comparison.iterrows():
        lines.append(
            f"- `{row['label']}`: v2 `{row['metric_v2']:.3f}` -> v3 `{row['metric_v3']:.3f}` (delta `{row['metric_v3'] - row['metric_v2']:+.3f}`)"
        )
    lines.extend(["", "## v2 vs v3 Early-Observable", ""])
    for _, row in early_comparison.iterrows():
        lines.append(
            f"- `{row['label']}`: v2 `{row['metric_v2']:.3f}` -> v3 `{row['metric_v3']:.3f}` (delta `{row['metric_v3'] - row['metric_v2']:+.3f}`)"
        )
    lines.extend(
        [
            "",
            "## Files",
            "",
            "- `v2_vs_v3_model_comparison.csv`",
            "- `v2_vs_v3_early_model_comparison.csv`",
            "- `selected_features_v3.csv`",
            "- `fullsample_model_summary_v3.csv`",
            "- `overlap_model_summary_v3.csv`",
            "- `fullsample_early_model_summary_v3.csv`",
            "- `overlap_early_model_summary_v3.csv`",
            "- `fullsample_model_coefficients_v3.csv`",
            "- `overlap_model_coefficients_v3.csv`",
            "- `v2_vs_v3_auc.png`",
            "- `v2_vs_v3_corr.png`",
        ]
    )
    (outdir / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Saved report: {outdir / 'summary.md'}")


if __name__ == "__main__":
    main()
