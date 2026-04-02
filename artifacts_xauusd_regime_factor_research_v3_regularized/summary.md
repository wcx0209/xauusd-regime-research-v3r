# XAUUSD Regime Factor Research v3 Regularized

This round keeps the v3 feature sets fixed and replaces unregularized models with time-series tuned L2 logistic regression and ridge regression.

## Main Comparison

- `full_high_vol_auc`: v2 `0.845` | v3 `0.900` | v3r `0.917`
- `full_trend_auc`: v2 `0.767` | v3 `0.902` | v3r `0.940`
- `full_regime_corr`: v2 `0.764` | v3 `0.884` | v3r `0.889`
- `overlap_high_vol_auc`: v2 `0.816` | v3 `0.732` | v3r `0.888`
- `overlap_trend_auc`: v2 `0.672` | v3 `0.862` | v3r `0.902`
- `overlap_regime_corr`: v2 `0.776` | v3 `0.890` | v3r `0.871`

## Early Comparison

- `full_early_high_vol_auc`: v2 `0.826` | v3 `0.795` | v3r `0.796`
- `full_early_regime_corr`: v2 `0.664` | v3 `0.656` | v3r `0.656`
- `overlap_early_high_vol_auc`: v2 `0.664` | v3 `0.728` | v3r `0.736`
- `overlap_early_regime_corr`: v2 `0.186` | v3 `0.220` | v3r `0.297`

## Files

- `v2_v3_v3r_model_comparison.csv`
- `v2_v3_v3r_early_model_comparison.csv`
- `fullsample_model_summary_v3r.csv`
- `overlap_model_summary_v3r.csv`
- `fullsample_early_model_summary_v3r.csv`
- `overlap_early_model_summary_v3r.csv`
- `fullsample_model_coefficients_v3r.csv`
- `overlap_model_coefficients_v3r.csv`
- `v2_v3_v3r_auc.png`
- `v2_v3_v3r_corr.png`