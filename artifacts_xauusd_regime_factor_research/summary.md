# XAUUSD Regime Factor Research

- MT5 sample: `2024-12-23` to `2026-04-02`
- Calendar+geo overlap sample: `2025-10-01` to `2026-03-31`
- Full-sample mean range ratio: `1.20`
- Overlap-sample mean range ratio: `1.36`

## Full Sample Top Drivers

- `DOLLAR_SHOCK`: `62` days, avg range ratio `1.58`, median `1.25`, range lift `41.8%`, high-vol rate `50.0%`, trend-day rate `33.9%`
- `DOLLAR_YIELD_CONFLUENCE`: `16` days, avg range ratio `1.57`, median `1.44`, range lift `32.8%`, high-vol rate `62.5%`, trend-day rate `43.8%`
- `CROSS_ASSET_ANY_SHOCK`: `173` days, avg range ratio `1.33`, median `1.11`, range lift `25.6%`, high-vol rate `38.2%`, trend-day rate `23.1%`
- `OIL_SHOCK`: `66` days, avg range ratio `1.43`, median `1.12`, range lift `24.7%`, high-vol rate `43.9%`, trend-day rate `24.2%`
- `SPX_SHOCK`: `60` days, avg range ratio `1.43`, median `1.28`, range lift `24.6%`, high-vol rate `50.0%`, trend-day rate `35.0%`
- `VIX_SHOCK`: `60` days, avg range ratio `1.43`, median `1.23`, range lift `23.9%`, high-vol rate `46.7%`, trend-day rate `35.0%`
- `OPEN_OUTSIDE_PREV_RANGE`: `27` days, avg range ratio `1.43`, median `1.07`, range lift `21.4%`, high-vol rate `40.7%`, trend-day rate `11.1%`
- `us_break_early`: `254` days, avg range ratio `1.24`, median `1.07`, range lift `18.2%`, high-vol rate `35.4%`, trend-day rate `22.8%`

## Overlap Sample Top Drivers

- `DOLLAR_SHOCK` (price_cross_asset): `16` days, avg range ratio `2.24`, median `1.44`, range lift `82.3%`, high-vol rate `62.5%`, trend-day rate `31.2%`
- `GEO_US_CHINA_TAIWAN_TRADE_SHOCK` (calendar_geo): `18` days, avg range ratio `1.74`, median `1.15`, range lift `34.3%`, high-vol rate `44.4%`, trend-day rate `16.7%`
- `GEO_ANY_SHOCK` (calendar_geo): `39` days, avg range ratio `1.63`, median `1.33`, range lift `32.5%`, high-vol rate `51.3%`, trend-day rate `35.9%`
- `OPEN_OUTSIDE_PREV_RANGE` (price_cross_asset): `13` days, avg range ratio `1.70`, median `1.14`, range lift `29.2%`, high-vol rate `46.2%`, trend-day rate `7.7%`
- `CROSS_ASSET_ANY_SHOCK` (price_cross_asset): `72` days, avg range ratio `1.49`, median `1.10`, range lift `26.9%`, high-vol rate `38.9%`, trend-day rate `22.2%`
- `GEO_RUSSIA_UKRAINE_SHOCK` (calendar_geo): `20` days, avg range ratio `1.62`, median `1.30`, range lift `24.1%`, high-vol rate `50.0%`, trend-day rate `35.0%`
- `europe_break_asia` (price_cross_asset): `99` days, avg range ratio `1.40`, median `1.09`, range lift `16.6%`, high-vol rate `37.4%`, trend-day rate `21.2%`
- `US_INFLATION` (calendar_geo): `14` days, avg range ratio `1.54`, median `0.92`, range lift `15.9%`, high-vol rate `21.4%`, trend-day rate `21.4%`
- `WEEKEND_GEO_CARRY` (calendar_geo): `26` days, avg range ratio `1.52`, median `1.17`, range lift `15.5%`, high-vol rate `46.2%`, trend-day rate `30.8%`
- `FED_POLICY` (calendar_geo): `8` days, avg range ratio `1.54`, median `1.34`, range lift `14.5%`, high-vol rate `50.0%`, trend-day rate `37.5%`

## Model Summary

- `fullsample_high_vol_logit`: OOS AUC `0.75`, train pseudo-R2 `0.12`
- `fullsample_trend_day_logit`: OOS AUC `0.70`, train pseudo-R2 `0.09`
- `fullsample_regime_score_ols`: OOS corr `0.25`, train R2 `0.18`
- `overlap_high_vol_logit`: OOS AUC `0.73`, train pseudo-R2 `0.27`
- `overlap_trend_day_logit`: OOS AUC `0.62`, train pseudo-R2 `0.31`
- `overlap_regime_score_ols`: OOS corr `0.45`, train R2 `0.32`

## Files

- `xau_regime_full_dataset.csv`
- `xau_regime_overlap_dataset.csv`
- `fullsample_factor_rank.csv`
- `overlap_factor_rank.csv`
- `fullsample_model_summary.csv`
- `overlap_model_summary.csv`
- `fullsample_model_coefficients.csv`
- `overlap_model_coefficients.csv`
- `fullsample_top_factors.png`
- `overlap_top_factors.png`
- `fullsample_highvol_coefficients.png`
- `overlap_highvol_coefficients.png`