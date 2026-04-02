# XAUUSD Regime Factor Research v3

This round keeps the v2 stack and adds external open-source proxies for ETF flow, COMEX activity, gold volatility, miners, credit, rates, and safe-haven FX.

## Selected External Additions

- `full_explain`: `prev_day_range_ratio,min_prev_extreme_dist_norm,OPEN_OUTSIDE_PREV_RANGE,range_ratio_europe,body_ratio_europe,london2h_range_ratio,london2h_break_prevday,us2h_range_ratio,dxy_abs_z20,tnx_abs_z20,vix_abs_z20,oil_abs_z20,dollar_yield_intensity,dollar_vix_intensity,gld_abs_z20`
- `overlap_explain`: `FED_POLICY_rows,US_INFLATION_rows,usd_high_total_rows,geo_total_score_z20_abs,GEO_MIDDLE_EAST_score_z20_abs,WEEKEND_GEO_CARRY,prev_day_range_ratio,OPEN_OUTSIDE_PREV_RANGE,range_ratio_europe,london2h_range_ratio,london2h_break_prevday,dxy_abs_z20,vix_abs_z20,dollar_vix_intensity,gld_flow_proxy,gld_abs_z20`
- `full_early`: `prev_day_range_ratio,min_prev_extreme_dist_norm,OPEN_OUTSIDE_PREV_RANGE,london2h_range_ratio,london2h_break_prevday,dxy_abs_z20_lag1,tnx_abs_z20_lag1,vix_abs_z20_lag1,oil_abs_z20_lag1,gc_volume_ratio20_lag1,gvz_abs_z20_lag1,jpy_ret_lag1`
- `overlap_early`: `WEEKEND_GEO_CARRY,prev_day_range_ratio,OPEN_OUTSIDE_PREV_RANGE,london2h_range_ratio,london2h_break_prevday,dxy_abs_z20_lag1,vix_abs_z20_lag1,geo_total_score_z20_abs_lag1,gold_vol_credit_intensity_lag1,jpy_ret_lag1`

## v2 vs v3

- `full_high_vol_auc`: v2 `0.845` -> v3 `0.900` (delta `+0.055`)
- `full_trend_auc`: v2 `0.767` -> v3 `0.902` (delta `+0.135`)
- `full_regime_corr`: v2 `0.764` -> v3 `0.884` (delta `+0.120`)
- `overlap_high_vol_auc`: v2 `0.816` -> v3 `0.732` (delta `-0.084`)
- `overlap_trend_auc`: v2 `0.672` -> v3 `0.862` (delta `+0.190`)
- `overlap_regime_corr`: v2 `0.776` -> v3 `0.890` (delta `+0.114`)

## v2 vs v3 Early-Observable

- `full_early_high_vol_auc`: v2 `0.826` -> v3 `0.795` (delta `-0.031`)
- `full_early_regime_corr`: v2 `0.664` -> v3 `0.656` (delta `-0.008`)
- `overlap_early_high_vol_auc`: v2 `0.664` -> v3 `0.728` (delta `+0.064`)
- `overlap_early_regime_corr`: v2 `0.186` -> v3 `0.220` (delta `+0.035`)

## Files

- `v2_vs_v3_model_comparison.csv`
- `v2_vs_v3_early_model_comparison.csv`
- `selected_features_v3.csv`
- `fullsample_model_summary_v3.csv`
- `overlap_model_summary_v3.csv`
- `fullsample_early_model_summary_v3.csv`
- `overlap_early_model_summary_v3.csv`
- `fullsample_model_coefficients_v3.csv`
- `overlap_model_coefficients_v3.csv`
- `v2_vs_v3_auc.png`
- `v2_vs_v3_corr.png`