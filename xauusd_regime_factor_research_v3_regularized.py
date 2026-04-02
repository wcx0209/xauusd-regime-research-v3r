from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import TimeSeriesSplit


ROOT = Path(__file__).resolve().parent
V2_ART = ROOT / "artifacts_xauusd_regime_factor_research_v2"
V3_ART = ROOT / "artifacts_xauusd_regime_factor_research_v3"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Regularized XAUUSD regime-factor v3 validation.")
    parser.add_argument("--outdir", default="artifacts_xauusd_regime_factor_research_v3_regularized")
    return parser.parse_args()


def load_selected_features() -> dict[str, list[str]]:
    rows = pd.read_csv(V3_ART / "selected_features_v3.csv")
    return {
        row["model_group"]: [item for item in str(row["selected_features"]).split(",") if item]
        for _, row in rows.iterrows()
    }


def standardize_pair(
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


def tune_logistic(
    train: pd.DataFrame,
    features: list[str],
    bool_features: set[str],
    target: str,
    c_grid: list[float],
) -> tuple[float, pd.DataFrame]:
    tscv = TimeSeriesSplit(n_splits=3)
    results = []
    for c_value in c_grid:
        scores = []
        for sub_idx, val_idx in tscv.split(train):
            subtrain = train.iloc[sub_idx].copy()
            val = train.iloc[val_idx].copy()
            if subtrain[target].nunique() < 2 or val[target].nunique() < 2:
                continue
            subtrain_std, val_std, _ = standardize_pair(subtrain, val, features, bool_features)
            model = LogisticRegression(C=c_value, solver="liblinear", max_iter=5000, random_state=42)
            model.fit(subtrain_std[features], subtrain_std[target].astype(int))
            pred = model.predict_proba(val_std[features])[:, 1]
            scores.append(float(roc_auc_score(val_std[target].astype(int), pred)))
        results.append({"hyperparam": c_value, "cv_metric": float(np.mean(scores)) if scores else np.nan})
    results_df = pd.DataFrame(results).sort_values("hyperparam").reset_index(drop=True)
    valid = results_df.dropna(subset=["cv_metric"])
    if valid.empty:
        return 1.0, results_df
    best_row = valid.sort_values(["cv_metric", "hyperparam"], ascending=[False, True]).iloc[0]
    return float(best_row["hyperparam"]), results_df


def tune_ridge(
    train: pd.DataFrame,
    features: list[str],
    bool_features: set[str],
    alpha_grid: list[float],
) -> tuple[float, pd.DataFrame]:
    tscv = TimeSeriesSplit(n_splits=3)
    results = []
    for alpha in alpha_grid:
        scores = []
        for sub_idx, val_idx in tscv.split(train):
            subtrain = train.iloc[sub_idx].copy()
            val = train.iloc[val_idx].copy()
            subtrain_std, val_std, _ = standardize_pair(subtrain, val, features, bool_features)
            model = Ridge(alpha=alpha)
            model.fit(subtrain_std[features], subtrain_std["regime_score"].astype(float))
            pred = pd.Series(model.predict(val_std[features]), index=val_std.index)
            corr = float(pred.corr(val_std["regime_score"].astype(float)))
            if np.isfinite(corr):
                scores.append(corr)
        results.append({"hyperparam": alpha, "cv_metric": float(np.mean(scores)) if scores else np.nan})
    results_df = pd.DataFrame(results).sort_values("hyperparam").reset_index(drop=True)
    valid = results_df.dropna(subset=["cv_metric"])
    if valid.empty:
        return 1.0, results_df
    best_row = valid.sort_values(["cv_metric", "hyperparam"], ascending=[False, True]).iloc[0]
    return float(best_row["hyperparam"]), results_df


def fit_regularized_suite(
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

    c_grid = [0.03, 0.1, 0.3, 1.0, 3.0, 10.0]
    alpha_grid = [0.03, 0.1, 0.3, 1.0, 3.0, 10.0, 30.0]

    high_c, high_cv = tune_logistic(train, features, bool_features, "high_vol_day", c_grid)
    trend_c, trend_cv = tune_logistic(train, features, bool_features, "trend_day", c_grid)
    regime_alpha, regime_cv = tune_ridge(train, features, bool_features, alpha_grid)

    train_std, test_std, params = standardize_pair(train, test, features, bool_features)
    full_std = standardize_full(df.copy(), features, bool_features, params)

    high_model = LogisticRegression(C=high_c, solver="liblinear", max_iter=5000, random_state=42)
    trend_model = LogisticRegression(C=trend_c, solver="liblinear", max_iter=5000, random_state=42)
    regime_model = Ridge(alpha=regime_alpha)

    high_model.fit(train_std[features], train_std["high_vol_day"].astype(int))
    trend_model.fit(train_std[features], train_std["trend_day"].astype(int))
    regime_model.fit(train_std[features], train_std["regime_score"].astype(float))

    high_pred = high_model.predict_proba(test_std[features])[:, 1]
    trend_pred = trend_model.predict_proba(test_std[features])[:, 1]
    regime_pred = pd.Series(regime_model.predict(test_std[features]), index=test_std.index)

    summary = pd.DataFrame(
        [
            {
                "model": f"{prefix}_high_vol_logit_v3r",
                "train_obs": len(train),
                "test_obs": len(test),
                "oos_auc": float(roc_auc_score(test_std["high_vol_day"].astype(int), high_pred)),
                "regularization": "l2",
                "hyperparam": high_c,
            },
            {
                "model": f"{prefix}_trend_day_logit_v3r",
                "train_obs": len(train),
                "test_obs": len(test),
                "oos_auc": float(roc_auc_score(test_std["trend_day"].astype(int), trend_pred)),
                "regularization": "l2",
                "hyperparam": trend_c,
            },
            {
                "model": f"{prefix}_regime_score_ridge_v3r",
                "train_obs": len(train),
                "test_obs": len(test),
                "oos_corr": float(regime_pred.corr(test_std["regime_score"].astype(float))),
                "regularization": "ridge",
                "hyperparam": regime_alpha,
            },
        ]
    )

    hyper_grid = []
    for target, cv_frame in [
        ("high_vol_day", high_cv),
        ("trend_day", trend_cv),
        ("regime_score", regime_cv),
    ]:
        for _, row in cv_frame.iterrows():
            hyper_grid.append(
                {
                    "model_group": prefix,
                    "target": target,
                    "hyperparam": row["hyperparam"],
                    "cv_metric": row["cv_metric"],
                }
            )
    pd.DataFrame(hyper_grid).to_csv(outdir / f"{prefix}_hyperparam_search_v3r.csv", index=False)

    full_train_std, _, full_params = standardize_pair(df.copy(), df.copy(), features, bool_features)
    full_high_model = LogisticRegression(C=high_c, solver="liblinear", max_iter=5000, random_state=42)
    full_trend_model = LogisticRegression(C=trend_c, solver="liblinear", max_iter=5000, random_state=42)
    full_regime_model = Ridge(alpha=regime_alpha)
    full_high_model.fit(full_train_std[features], full_train_std["high_vol_day"].astype(int))
    full_trend_model.fit(full_train_std[features], full_train_std["trend_day"].astype(int))
    full_regime_model.fit(full_train_std[features], full_train_std["regime_score"].astype(float))

    coef_rows = []
    for model_name, coef_vector in [
        (f"{prefix}_high_vol_logit_v3r", full_high_model.coef_[0]),
        (f"{prefix}_trend_day_logit_v3r", full_trend_model.coef_[0]),
        (f"{prefix}_regime_score_ridge_v3r", full_regime_model.coef_),
    ]:
        for feature, coef in zip(features, coef_vector):
            coef_rows.append({"model": model_name, "feature": feature, "coef": float(coef)})

    return summary, pd.DataFrame(coef_rows)


def plot_comparison(comp: pd.DataFrame, metric: str, title: str, outpath: Path) -> None:
    fig, ax = plt.subplots(figsize=(8.8, 4.8))
    x = np.arange(len(comp))
    width = 0.25
    ax.bar(x - width, comp[f"{metric}_v2"], width=width, color="#0f766e", label="v2")
    ax.bar(x, comp[f"{metric}_v3"], width=width, color="#1d4ed8", label="v3")
    ax.bar(x + width, comp[f"{metric}_v3r"], width=width, color="#7c3aed", label="v3r")
    ax.set_xticks(x)
    ax.set_xticklabels(comp["label"])
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

    selected = load_selected_features()
    full = pd.read_csv(V3_ART / "xau_regime_full_dataset_v3.csv", parse_dates=["date"])
    overlap = pd.read_csv(V3_ART / "xau_regime_overlap_dataset_v3.csv", parse_dates=["date"])

    bool_map = {
        "full_explain": {"OPEN_OUTSIDE_PREV_RANGE", "london2h_break_prevday"},
        "overlap_explain": {"WEEKEND_GEO_CARRY", "OPEN_OUTSIDE_PREV_RANGE", "london2h_break_prevday"},
        "full_early": {"OPEN_OUTSIDE_PREV_RANGE", "london2h_break_prevday"},
        "overlap_early": {"WEEKEND_GEO_CARRY", "OPEN_OUTSIDE_PREV_RANGE", "london2h_break_prevday"},
    }

    full_summary_v3r, full_coef_v3r = fit_regularized_suite(
        full, selected["full_explain"], bool_map["full_explain"], "fullsample", outdir
    )
    overlap_summary_v3r, overlap_coef_v3r = fit_regularized_suite(
        overlap, selected["overlap_explain"], bool_map["overlap_explain"], "overlap", outdir
    )
    full_early_summary_v3r, full_early_coef_v3r = fit_regularized_suite(
        full, selected["full_early"], bool_map["full_early"], "fullsample_early", outdir
    )
    overlap_early_summary_v3r, overlap_early_coef_v3r = fit_regularized_suite(
        overlap, selected["overlap_early"], bool_map["overlap_early"], "overlap_early", outdir
    )

    full_summary_v3r.to_csv(outdir / "fullsample_model_summary_v3r.csv", index=False)
    overlap_summary_v3r.to_csv(outdir / "overlap_model_summary_v3r.csv", index=False)
    full_early_summary_v3r.to_csv(outdir / "fullsample_early_model_summary_v3r.csv", index=False)
    overlap_early_summary_v3r.to_csv(outdir / "overlap_early_model_summary_v3r.csv", index=False)
    full_coef_v3r.to_csv(outdir / "fullsample_model_coefficients_v3r.csv", index=False)
    overlap_coef_v3r.to_csv(outdir / "overlap_model_coefficients_v3r.csv", index=False)
    full_early_coef_v3r.to_csv(outdir / "fullsample_early_model_coefficients_v3r.csv", index=False)
    overlap_early_coef_v3r.to_csv(outdir / "overlap_early_model_coefficients_v3r.csv", index=False)

    v2_main = pd.read_csv(V3_ART / "v2_vs_v3_model_comparison.csv")
    v2_early = pd.read_csv(V3_ART / "v2_vs_v3_early_model_comparison.csv")

    main_comp = pd.DataFrame(
        [
            {
                "label": "full_high_vol_auc",
                "metric": "auc",
                "metric_v2": float(v2_main.loc[v2_main["label"] == "full_high_vol_auc", "metric_v2"].iloc[0]),
                "metric_v3": float(v2_main.loc[v2_main["label"] == "full_high_vol_auc", "metric_v3"].iloc[0]),
                "metric_v3r": float(full_summary_v3r.loc[full_summary_v3r["model"] == "fullsample_high_vol_logit_v3r", "oos_auc"].iloc[0]),
            },
            {
                "label": "full_trend_auc",
                "metric": "auc",
                "metric_v2": float(v2_main.loc[v2_main["label"] == "full_trend_auc", "metric_v2"].iloc[0]),
                "metric_v3": float(v2_main.loc[v2_main["label"] == "full_trend_auc", "metric_v3"].iloc[0]),
                "metric_v3r": float(full_summary_v3r.loc[full_summary_v3r["model"] == "fullsample_trend_day_logit_v3r", "oos_auc"].iloc[0]),
            },
            {
                "label": "full_regime_corr",
                "metric": "corr",
                "metric_v2": float(v2_main.loc[v2_main["label"] == "full_regime_corr", "metric_v2"].iloc[0]),
                "metric_v3": float(v2_main.loc[v2_main["label"] == "full_regime_corr", "metric_v3"].iloc[0]),
                "metric_v3r": float(full_summary_v3r.loc[full_summary_v3r["model"] == "fullsample_regime_score_ridge_v3r", "oos_corr"].iloc[0]),
            },
            {
                "label": "overlap_high_vol_auc",
                "metric": "auc",
                "metric_v2": float(v2_main.loc[v2_main["label"] == "overlap_high_vol_auc", "metric_v2"].iloc[0]),
                "metric_v3": float(v2_main.loc[v2_main["label"] == "overlap_high_vol_auc", "metric_v3"].iloc[0]),
                "metric_v3r": float(overlap_summary_v3r.loc[overlap_summary_v3r["model"] == "overlap_high_vol_logit_v3r", "oos_auc"].iloc[0]),
            },
            {
                "label": "overlap_trend_auc",
                "metric": "auc",
                "metric_v2": float(v2_main.loc[v2_main["label"] == "overlap_trend_auc", "metric_v2"].iloc[0]),
                "metric_v3": float(v2_main.loc[v2_main["label"] == "overlap_trend_auc", "metric_v3"].iloc[0]),
                "metric_v3r": float(overlap_summary_v3r.loc[overlap_summary_v3r["model"] == "overlap_trend_day_logit_v3r", "oos_auc"].iloc[0]),
            },
            {
                "label": "overlap_regime_corr",
                "metric": "corr",
                "metric_v2": float(v2_main.loc[v2_main["label"] == "overlap_regime_corr", "metric_v2"].iloc[0]),
                "metric_v3": float(v2_main.loc[v2_main["label"] == "overlap_regime_corr", "metric_v3"].iloc[0]),
                "metric_v3r": float(overlap_summary_v3r.loc[overlap_summary_v3r["model"] == "overlap_regime_score_ridge_v3r", "oos_corr"].iloc[0]),
            },
        ]
    )
    early_comp = pd.DataFrame(
        [
            {
                "label": "full_early_high_vol_auc",
                "metric": "auc",
                "metric_v2": float(v2_early.loc[v2_early["label"] == "full_early_high_vol_auc", "metric_v2"].iloc[0]),
                "metric_v3": float(v2_early.loc[v2_early["label"] == "full_early_high_vol_auc", "metric_v3"].iloc[0]),
                "metric_v3r": float(full_early_summary_v3r.loc[full_early_summary_v3r["model"] == "fullsample_early_high_vol_logit_v3r", "oos_auc"].iloc[0]),
            },
            {
                "label": "full_early_regime_corr",
                "metric": "corr",
                "metric_v2": float(v2_early.loc[v2_early["label"] == "full_early_regime_corr", "metric_v2"].iloc[0]),
                "metric_v3": float(v2_early.loc[v2_early["label"] == "full_early_regime_corr", "metric_v3"].iloc[0]),
                "metric_v3r": float(full_early_summary_v3r.loc[full_early_summary_v3r["model"] == "fullsample_early_regime_score_ridge_v3r", "oos_corr"].iloc[0]),
            },
            {
                "label": "overlap_early_high_vol_auc",
                "metric": "auc",
                "metric_v2": float(v2_early.loc[v2_early["label"] == "overlap_early_high_vol_auc", "metric_v2"].iloc[0]),
                "metric_v3": float(v2_early.loc[v2_early["label"] == "overlap_early_high_vol_auc", "metric_v3"].iloc[0]),
                "metric_v3r": float(overlap_early_summary_v3r.loc[overlap_early_summary_v3r["model"] == "overlap_early_high_vol_logit_v3r", "oos_auc"].iloc[0]),
            },
            {
                "label": "overlap_early_regime_corr",
                "metric": "corr",
                "metric_v2": float(v2_early.loc[v2_early["label"] == "overlap_early_regime_corr", "metric_v2"].iloc[0]),
                "metric_v3": float(v2_early.loc[v2_early["label"] == "overlap_early_regime_corr", "metric_v3"].iloc[0]),
                "metric_v3r": float(overlap_early_summary_v3r.loc[overlap_early_summary_v3r["model"] == "overlap_early_regime_score_ridge_v3r", "oos_corr"].iloc[0]),
            },
        ]
    )
    main_comp.to_csv(outdir / "v2_v3_v3r_model_comparison.csv", index=False)
    early_comp.to_csv(outdir / "v2_v3_v3r_early_model_comparison.csv", index=False)

    plot_comparison(
        main_comp.loc[main_comp["metric"] == "auc"].rename(columns={"metric_v2": "auc_v2", "metric_v3": "auc_v3", "metric_v3r": "auc_v3r"}),
        "auc",
        "XAUUSD Regime Models: v2 vs v3 vs v3r AUC",
        outdir / "v2_v3_v3r_auc.png",
    )
    plot_comparison(
        pd.concat(
            [
                main_comp.loc[main_comp["metric"] == "corr", ["label", "metric_v2", "metric_v3", "metric_v3r"]],
                early_comp.loc[early_comp["metric"] == "corr", ["label", "metric_v2", "metric_v3", "metric_v3r"]],
            ],
            ignore_index=True,
        ).rename(columns={"metric_v2": "corr_v2", "metric_v3": "corr_v3", "metric_v3r": "corr_v3r"}),
        "corr",
        "XAUUSD Regime Models: v2 vs v3 vs v3r OOS Correlation",
        outdir / "v2_v3_v3r_corr.png",
    )

    lines = [
        "# XAUUSD Regime Factor Research v3 Regularized",
        "",
        "This round keeps the v3 feature sets fixed and replaces unregularized models with time-series tuned L2 logistic regression and ridge regression.",
        "",
        "## Main Comparison",
        "",
    ]
    for _, row in main_comp.iterrows():
        lines.append(
            f"- `{row['label']}`: v2 `{row['metric_v2']:.3f}` | v3 `{row['metric_v3']:.3f}` | v3r `{row['metric_v3r']:.3f}`"
        )
    lines.extend(["", "## Early Comparison", ""])
    for _, row in early_comp.iterrows():
        lines.append(
            f"- `{row['label']}`: v2 `{row['metric_v2']:.3f}` | v3 `{row['metric_v3']:.3f}` | v3r `{row['metric_v3r']:.3f}`"
        )
    lines.extend(
        [
            "",
            "## Files",
            "",
            "- `v2_v3_v3r_model_comparison.csv`",
            "- `v2_v3_v3r_early_model_comparison.csv`",
            "- `fullsample_model_summary_v3r.csv`",
            "- `overlap_model_summary_v3r.csv`",
            "- `fullsample_early_model_summary_v3r.csv`",
            "- `overlap_early_model_summary_v3r.csv`",
            "- `fullsample_model_coefficients_v3r.csv`",
            "- `overlap_model_coefficients_v3r.csv`",
            "- `v2_v3_v3r_auc.png`",
            "- `v2_v3_v3r_corr.png`",
        ]
    )
    (outdir / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Saved report: {outdir / 'summary.md'}")


if __name__ == "__main__":
    main()
