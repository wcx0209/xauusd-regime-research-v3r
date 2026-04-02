# XAUUSD Calendar + Geopolitical Regime Analysis

Sample: `2025-10-01` to `2026-03-31` using local `XAUUSD M15` MT5 bars and the MQL5 native calendar.

## Baseline

- Mean daily range ratio vs prior-20-day median: `1.36`
- High-volatility day rate (`range_ratio >= 1.25`): `35.9%`
- Trend-day rate (`range_ratio >= 1.25` and `body_ratio >= 0.55`): `19.5%`

## Top Macro Families

- `US_INFLATION`: `14` days, mean range ratio `1.54`, range lift `15.9%`, high-vol rate `21.4%`, trend-day rate `21.4%`
- `FED_POLICY`: `8` days, mean range ratio `1.54`, range lift `14.5%`, high-vol rate `50.0%`, trend-day rate `37.5%`
- `BOJ_POLICY`: `4` days, mean range ratio `1.49`, range lift `10.2%`, high-vol rate `25.0%`, trend-day rate `0.0%`
- `US_GROWTH_ACTIVITY`: `40` days, mean range ratio `1.37`, range lift `1.5%`, high-vol rate `30.0%`, trend-day rate `15.0%`
- `USD_HIGH_ANY`: `81` days, mean range ratio `1.35`, range lift `-1.5%`, high-vol rate `32.1%`, trend-day rate `18.5%`

## Top Geopolitical Shock Families

- `GEO_KOREA_PENINSULA_PURE`: `9` pure geo days, mean range ratio `1.63`, range lift `24.5%`, high-vol rate `44.4%`, trend-day rate `22.2%`
- `GEO_INDIA_PAKISTAN_PURE`: `7` pure geo days, mean range ratio `1.48`, range lift `9.8%`, high-vol rate `57.1%`, trend-day rate `28.6%`
- `GEO_MIDDLE_EAST_PURE`: `11` pure geo days, mean range ratio `1.43`, range lift `5.7%`, high-vol rate `45.5%`, trend-day rate `27.3%`
- `GEO_RUSSIA_UKRAINE_PURE`: `10` pure geo days, mean range ratio `1.37`, range lift `0.5%`, high-vol rate `50.0%`, trend-day rate `30.0%`
- `GEO_US_CHINA_TAIWAN_TRADE_PURE`: `8` pure geo days, mean range ratio `1.16`, range lift `-18.1%`, high-vol rate `37.5%`, trend-day rate `25.0%`

## Example Geopolitical Shock Dates

- `GEO_INDIA_PAKISTAN` trading day `2026-03-02` (source dates `2026-02-28,2026-03-01,2026-03-02`) score `165.0`: 2026-02-28 ) (Saturday) edit history watch Armed conflicts and attacks 2026 Iran war Israel launches an attack on Iran , calling it a preemptive strike , killing several Iranian high-ranking officials including supreme leader Ali Khamenei . (CNN) (NBC News) Th
- `GEO_INDIA_PAKISTAN` trading day `2026-03-30` (source dates `2026-03-28,2026-03-29,2026-03-30`) score `74.5`: 2026-03-28 ) (Saturday) edit history watch Armed conflicts and attacks Middle Eastern crisis 2026 Iran war 2026 Iranian strikes on Bahrain The smelter facility of Aluminium Bahrain in Askar , Southern Governorate , is targeted by Iranian attacks. (CNBC) 2026 I
- `GEO_INDIA_PAKISTAN` trading day `2026-03-09` (source dates `2026-03-07,2026-03-08,2026-03-09`) score `69.0`: 2026-03-07 ) (Saturday) edit history watch Armed conflicts and attacks Middle Eastern crisis 2026 Iran war 2025–2026 Iran–United States negotiations Iranian ambassador to Russia Kazem Jalali says that Iran is ready for normal talks but also rejects the current
- `GEO_KOREA_PENINSULA` trading day `2026-03-02` (source dates `2026-02-28,2026-03-01,2026-03-02`) score `81.0`: 2026-02-28 ) (Saturday) edit history watch Armed conflicts and attacks 2026 Iran war Israel launches an attack on Iran , calling it a preemptive strike , killing several Iranian high-ranking officials including supreme leader Ali Khamenei . (CNN) (NBC News) Th
- `GEO_KOREA_PENINSULA` trading day `2026-03-09` (source dates `2026-03-07,2026-03-08,2026-03-09`) score `31.5`: 2026-03-07 ) (Saturday) edit history watch Armed conflicts and attacks Middle Eastern crisis 2026 Iran war 2025–2026 Iran–United States negotiations Iranian ambassador to Russia Kazem Jalali says that Iran is ready for normal talks but also rejects the current
- `GEO_KOREA_PENINSULA` trading day `2026-03-23` (source dates `2026-03-21,2026-03-22,2026-03-23`) score `26.5`: 2026-03-21 ) (Saturday) edit history watch Armed conflicts and attacks Middle Eastern crisis 2026 Iran war Attack on Natanz nuclear facility Israeli and U.S. jets strike the Natanz Nuclear Facility , according to the Atomic Energy Organization of Iran . (Al Ja
- `GEO_MIDDLE_EAST` trading day `2026-03-02` (source dates `2026-02-28,2026-03-01,2026-03-02`) score `288.0`: 2026-02-28 ) (Saturday) edit history watch Armed conflicts and attacks 2026 Iran war Israel launches an attack on Iran , calling it a preemptive strike , killing several Iranian high-ranking officials including supreme leader Ali Khamenei . (CNN) (NBC News) Th
- `GEO_MIDDLE_EAST` trading day `2026-03-30` (source dates `2026-03-28,2026-03-29,2026-03-30`) score `188.0`: 2026-03-28 ) (Saturday) edit history watch Armed conflicts and attacks Middle Eastern crisis 2026 Iran war 2026 Iranian strikes on Bahrain The smelter facility of Aluminium Bahrain in Askar , Southern Governorate , is targeted by Iranian attacks. (CNBC) 2026 I
- `GEO_MIDDLE_EAST` trading day `2026-03-16` (source dates `2026-03-14,2026-03-15,2026-03-16`) score `148.5`: 2026-03-14 ) (Saturday) edit history watch Armed conflicts and attacks Middle Eastern crisis 2026 Iran war 2026 Iranian strikes on Saudi Arabia Five U.S. warplanes are damaged in an Iranian drone strike on Prince Sultan Air Base , Saudi Arabia . ( The Wall Str
- `GEO_RUSSIA_UKRAINE` trading day `2026-03-02` (source dates `2026-02-28,2026-03-01,2026-03-02`) score `185.5`: 2026-02-28 ) (Saturday) edit history watch Armed conflicts and attacks 2026 Iran war Israel launches an attack on Iran , calling it a preemptive strike , killing several Iranian high-ranking officials including supreme leader Ali Khamenei . (CNN) (NBC News) Th
- `GEO_RUSSIA_UKRAINE` trading day `2026-03-30` (source dates `2026-03-28,2026-03-29,2026-03-30`) score `120.0`: 2026-03-28 ) (Saturday) edit history watch Armed conflicts and attacks Middle Eastern crisis 2026 Iran war 2026 Iranian strikes on Bahrain The smelter facility of Aluminium Bahrain in Askar , Southern Governorate , is targeted by Iranian attacks. (CNBC) 2026 I
- `GEO_RUSSIA_UKRAINE` trading day `2026-03-16` (source dates `2026-03-14,2026-03-15,2026-03-16`) score `95.5`: 2026-03-14 ) (Saturday) edit history watch Armed conflicts and attacks Middle Eastern crisis 2026 Iran war 2026 Iranian strikes on Saudi Arabia Five U.S. warplanes are damaged in an Iranian drone strike on Prince Sultan Air Base , Saudi Arabia . ( The Wall Str
- `GEO_US_CHINA_TAIWAN_TRADE` trading day `2026-03-02` (source dates `2026-02-28,2026-03-01,2026-03-02`) score `31.0`: 2026-02-28 ) (Saturday) edit history watch Armed conflicts and attacks 2026 Iran war Israel launches an attack on Iran , calling it a preemptive strike , killing several Iranian high-ranking officials including supreme leader Ali Khamenei . (CNN) (NBC News) Th
- `GEO_US_CHINA_TAIWAN_TRADE` trading day `2025-12-29` (source dates `2025-12-27,2025-12-28,2025-12-29`) score `22.5`: 2025-12-27 ) (Saturday) edit history watch Armed conflicts and attacks Russo-Ukrainian war Kyiv strikes , Russian strikes against Ukrainian infrastructure Two people are killed and 32 are injured during a Russian missile and drone strike on Kyiv , Ukraine . Da
- `GEO_US_CHINA_TAIWAN_TRADE` trading day `2026-02-02` (source dates `2026-01-31,2026-02-01,2026-02-02`) score `21.0`: 2026-01-31 ) (Saturday) edit history watch Armed conflicts and attacks Gaza war Israeli bombing of the Gaza Strip At least 31 Palestinians , including at least six children, are killed from Israeli attacks in the Gaza Strip . (Al Jazeera) 2026 Balochistan atta

## Files

- `xau_daily_regime_with_events.csv`
- `macro_event_impact_rank.csv`
- `geo_event_impact_rank.csv`
- `combined_event_impact_rank.csv`
- `geo_theme_examples.csv`
- `macro_event_range_lift.png`
- `geo_event_range_lift_pure.png`