# XAUUSD Regime Research V3R

This repository packages the XAUUSD intraday regime research workflow, the V3R regularized regime identifier, the realtime desktop dashboard, and the associated Chinese research papers.

## Included

- `xauusd_realtime_regime_identifier.py`: stage-aware realtime regime scorer built on the V3R research outputs.
- `xauusd_realtime_regime_dashboard.py`: Tk desktop window that refreshes every 5 minutes and shows the live regime result with human-readable driver explanations.
- `xauusd_regime_factor_research.py` through `xauusd_regime_factor_research_v3_regularized.py`: the empirical research pipeline from baseline to regularized V3R.
- `xauusd_calendar_geo_regime_analysis.py`: macro-calendar and geopolitics regime study.
- `CodexXAUUSDRangeTrendOverlayEA.mq5`: the XAUUSD trading EA referenced by the strategy report.
- `XAUUSD盘中波动Regime驱动因素研究_基于MT5与开源多因子数据的实证分析.pdf`: the Chinese paper for the regime-factor study.
- `XAUUSD趋势叠加区间策略_MT5实证报告.pdf`: the Chinese paper for the XAUUSD strategy system.
- `artifacts_*` and `report_xau_paper/`: selected research outputs, model summaries, and paper figures used by the scripts and papers.

## Structure

- `data/`: local calendar export used by the research scripts.
- `artifacts_xauusd_*`: saved datasets, model summaries, and validation outputs.
- `report_xau_paper/`: paper figures.
- top-level Python scripts: reproducible research pipeline and realtime tools.

## Environment

Recommended Python version: `3.11`

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

## Realtime Dashboard

The realtime dashboard expects a locally installed MetaTrader 5 terminal and access to live `XAUUSD` data.

Run from PowerShell:

```powershell
python .\xauusd_realtime_regime_dashboard.py
```

Or double-click:

```text
Launch-XAURealtimeRegimeDashboard.bat
```

## Realtime CLI

```powershell
python .\xauusd_realtime_regime_identifier.py --loop --interval-minutes 5
```

## Notes

- The bundled `data/codex_native_calendar_majors.csv` is a local export copy so the research can be reproduced without relying on the original roaming path.
- MT5-dependent scripts may still need a custom `--terminal-path` depending on the local terminal installation.
- The papers are written in Chinese; the code comments and README are kept concise and operational.
