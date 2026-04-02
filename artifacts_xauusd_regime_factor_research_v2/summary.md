# XAUUSD Regime Factor Research v2

This round adds intensity variables, London/New York first-two-hour microstructure, and interaction terms on top of the original v1 factor stack.

## v1 vs v2

- `full_high_vol_auc`: v1 `0.750` -> v2 `0.845` (delta `+0.096`)
- `full_trend_auc`: v1 `0.697` -> v2 `0.767` (delta `+0.070`)
- `full_regime_corr`: v1 `0.248` -> v2 `0.764` (delta `+0.515`)
- `overlap_high_vol_auc`: v1 `0.728` -> v2 `0.816` (delta `+0.088`)
- `overlap_trend_auc`: v1 `0.625` -> v2 `0.672` (delta `+0.047`)
- `overlap_regime_corr`: v1 `0.453` -> v2 `0.776` (delta `+0.323`)

## Top v2 High-Vol Drivers

- `fullsample us2h_range_ratio`: coef `1.103`, p-value `0.000`
- `fullsample london2h_break_prevday`: coef `1.034`, p-value `0.005`
- `fullsample range_ratio_europe`: coef `0.906`, p-value `0.001`
- `fullsample london2h_range_ratio`: coef `0.545`, p-value `0.018`
- `fullsample dollar_vix_intensity`: coef `0.268`, p-value `0.548`
- `fullsample vix_abs_z20`: coef `0.230`, p-value `0.486`
- `fullsample tnx_abs_z20`: coef `0.193`, p-value `0.464`
- `fullsample dxy_abs_z20`: coef `0.152`, p-value `0.593`
- `overlap WEEKEND_GEO_CARRY`: coef `2.896`, p-value `0.026`
- `overlap range_ratio_europe`: coef `2.710`, p-value `0.003`
- `overlap london2h_range_ratio`: coef `1.311`, p-value `0.071`
- `overlap vix_abs_z20`: coef `0.905`, p-value `0.075`
- `overlap dxy_abs_z20`: coef `0.853`, p-value `0.098`
- `overlap london2h_break_prevday`: coef `0.526`, p-value `0.416`
- `overlap prev_day_range_ratio`: coef `0.068`, p-value `0.897`
- `overlap geo_total_score_z20_abs`: coef `0.061`, p-value `0.932`

## Early-Observable Sanity Check

- `full_early_high_vol_auc`: `0.826`
- `full_early_regime_corr`: `0.664`
- `overlap_early_high_vol_auc`: `0.664`
- `overlap_early_regime_corr`: `0.186`

## Files

- `xau_regime_full_dataset_v2.csv`
- `xau_regime_overlap_dataset_v2.csv`
- `fullsample_model_summary_v2.csv`
- `overlap_model_summary_v2.csv`
- `fullsample_model_coefficients_v2.csv`
- `overlap_model_coefficients_v2.csv`
- `v1_vs_v2_model_comparison.csv`
- `v2_early_model_comparison.csv`
- `v1_vs_v2_auc.png`
- `v1_vs_v2_corr.png`