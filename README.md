# XAUUSD 日内 Regime 研究与实时识别

这个仓库整理了我围绕 `XAUUSD` 做的一整套研究工作，重点包括：

- 用 `MT5` 本地数据研究黄金日内波动 `regime`
- 从 `v1 -> v2 -> v3 -> v3r` 逐步构建并验证多因子模型
- 做一个可以实时运行的 `Regime Identifier`
- 把研究结果写成中文论文和策略报告
- 给出一个基于研究结果的 `MT5 EA`

如果你是第一次打开这个仓库，最值得先看的有 4 个入口：

- [实时界面脚本](./xauusd_realtime_regime_dashboard.py)
- [实时识别脚本](./xauusd_realtime_regime_identifier.py)
- [Regime 因子论文 PDF](./XAUUSD盘中波动Regime驱动因素研究_基于MT5与开源多因子数据的实证分析.pdf)
- [策略报告 PDF](./XAUUSD趋势叠加区间策略_MT5实证报告.pdf)

## 这个项目在做什么

核心问题很简单：

`黄金今天更像低波动震荡日，还是更像高波动趋势日？`

为了回答这个问题，项目把影响 `XAUUSD` 日内状态的因素拆成几类来研究：

- 宏观日历事件
- 地缘冲击
- 美元与跨资产冲击
- 盘前和盘中的价格结构
- `GLD / COMEX / GVZ / JPY` 这类外部代理变量

在这个基础上，项目最后做出了两类可直接使用的产物：

- 一个研究用的 `V3R` 正则化 regime 模型
- 一个本地可运行、每 5 分钟自动刷新的实时桌面界面

## 目录说明

- `xauusd_realtime_regime_dashboard.py`
  说明：
  实时桌面窗口，直接显示 `Stage / Label / HighVol / Trend / RegimeScore`，并附带 `Top Drivers` 的中文解释。

- `xauusd_realtime_regime_identifier.py`
  说明：
  命令行版实时识别器，适合循环运行或做自动化桥接。

- `xauusd_regime_factor_research.py`
  说明：
  第一版综合因子研究。

- `xauusd_regime_factor_research_v2.py`
  说明：
  引入伦敦盘和美盘早段价格结构后的增强版。

- `xauusd_regime_factor_research_v3.py`
  说明：
  引入 `GLD / COMEX / GVZ / JPY` 外部代理变量后的扩展版。

- `xauusd_regime_factor_research_v3_regularized.py`
  说明：
  `V3R`，也就是正则化后的稳定版本，是当前最推荐参考的研究结果。

- `xauusd_calendar_geo_regime_analysis.py`
  说明：
  专门研究宏观日历和地缘事件如何影响黄金日内 regime。

- `CodexXAUUSDRangeTrendOverlayEA.mq5`
  说明：
  对应策略报告里的 `MT5 EA` 源码。

- `data/`
  说明：
  仓库内置的日历 CSV 副本，避免依赖原始 Roaming 目录。

- `artifacts_xauusd_*`
  说明：
  研究中间产物、模型摘要、排行、验证结果和输出图表。

- `report_xau_paper/`
  说明：
  论文里用到的图表文件。

## 快速开始

### 1. 环境准备

建议环境：

- `Python 3.11`
- 本机已安装 `MetaTrader 5`
- MT5 终端里能读取到 `XAUUSD` 数据

安装依赖：

```powershell
python -m pip install -r requirements.txt
```

### 2. 启动实时桌面界面

进入仓库目录后运行：

```powershell
python .\xauusd_realtime_regime_dashboard.py
```

如果你喜欢双击启动，可以直接运行：

```text
Launch-XAURealtimeRegimeDashboard.bat
```

### 3. 启动命令行循环识别器

```powershell
python .\xauusd_realtime_regime_identifier.py --loop --interval-minutes 5
```

### 4. 重新生成论文

先生成论文正文和图表，再导出 PDF：

```powershell
python .\build_xau_regime_factor_paper.py
python .\export_xau_regime_factor_paper_pdf.py
```

如果你要生成策略报告相关图表与 PDF：

```powershell
python .\build_xau_paper_figures.py
python .\export_xau_paper_pdf.py
```

## 推荐阅读顺序

如果你更关心研究逻辑：

1. 先看 [Regime 因子论文 PDF](./XAUUSD盘中波动Regime驱动因素研究_基于MT5与开源多因子数据的实证分析.pdf)
2. 再看 [xauusd_regime_factor_research_v3_regularized.py](./xauusd_regime_factor_research_v3_regularized.py)
3. 最后看 [xauusd_realtime_regime_identifier.py](./xauusd_realtime_regime_identifier.py)

如果你更关心实盘使用：

1. 先看 [xauusd_realtime_regime_dashboard.py](./xauusd_realtime_regime_dashboard.py)
2. 再看 [策略报告 PDF](./XAUUSD趋势叠加区间策略_MT5实证报告.pdf)
3. 最后看 [CodexXAUUSDRangeTrendOverlayEA.mq5](./CodexXAUUSDRangeTrendOverlayEA.mq5)

## 输出文件在哪里

实时识别器和桌面界面都会把最新结果写到：

- [artifacts_xauusd_realtime_regime_identifier/latest_regime_snapshot.json](./artifacts_xauusd_realtime_regime_identifier/latest_regime_snapshot.json)
- [artifacts_xauusd_realtime_regime_identifier/latest_regime_snapshot.md](./artifacts_xauusd_realtime_regime_identifier/latest_regime_snapshot.md)
- [artifacts_xauusd_realtime_regime_identifier/regime_snapshot_history.jsonl](./artifacts_xauusd_realtime_regime_identifier/regime_snapshot_history.jsonl)

## 注意事项

- 这套研究默认依赖本机 `MT5` 数据，所以换券商或换终端后，结果可能略有差异。
- 仓库里已经附带 `data/codex_native_calendar_majors.csv`，但如果你有更新的日历导出文件，也可以用 `--calendar-path` 自己指定。
- 如果你的 MT5 不在默认路径，运行脚本时加上 `--terminal-path` 即可。
- `artifacts_*` 目录里保存了不少研究结果，是论文和实时识别器要用到的，不建议随意删除。

## 适合谁

这个仓库比较适合：

- 想研究黄金日内波动 regime 的交易员
- 想把论文结论转成实时工具的人
- 想把 `MT5 + Python + 开源事件数据` 结合起来做实证研究的人

如果你只是想直接看结果，不想先读代码：

- 看论文 PDF
- 跑实时桌面界面
- 再决定是否深入看研究脚本
