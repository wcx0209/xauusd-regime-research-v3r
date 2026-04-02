# XAUUSD盘中波动Regime的决定因素、可交易性与正则化扩展
## 基于MT5与开源多因子数据的实证研究

### 摘要
本文基于本地 `MetaTrader 5` 终端中的 `XAUUSD M15` 数据，系统研究黄金盘中波动 regime 的决定因素，并将研究分为四个递进层次：`v1` 基础因子模型、`v2` 微观结构增强模型、`v3` 外部代理扩展模型，以及以时间序列交叉验证选择超参数的 `v3r` 正则化模型。样本由两部分组成：`2024-12-23` 至 `2026-04-02` 的长样本，以及 `2025-10-01` 至 `2026-03-31` 的重叠样本。前者用于识别价格结构、时段结构与跨资产冲击，后者进一步叠加 `MQL5` 原生日历与开源地缘事件。结果显示：第一，美元与跨资产冲击仍是黄金高波动 regime 的基础驱动力；第二，`v2` 通过引入伦敦/纽约前两小时的价格发现信息，大幅提升了解释力；第三，`v3` 新增的 `GLD`、`COMEX`、`GVZ` 与 `JPY` 等外部代理，能够进一步改善模型，尤其是在重叠样本与事件型波动环境下；第四，`v3` 中一部分看似显著的提升带有分离风险，而 `v3r` 经正则化后仍保留主要增益，说明新增信息并非纯粹过拟合。最终，`v3r` 在长样本中的高波动日样本外 `AUC` 达到 `0.917`，趋势日 `AUC` 达到 `0.940`，`regime_score` 样本外相关系数达到 `0.889`；在重叠样本中，上述三项分别为 `0.888`、`0.902` 和 `0.871`。但早期可交易模型的提升明显低于解释模型，说明黄金 regime 仍然高度依赖欧洲盘早段的同日价格发现。本文据此认为，黄金盘中 regime 的最优建模框架应为“两阶段结构”：先用隔夜与开盘前因子给出先验概率，再由伦敦前两小时的价格结构进行确认。

**关键词**：黄金；XAUUSD；波动 Regime；正则化；美元冲击；地缘政治；市场微观结构；GLD；COMEX；GVZ

## 1. 引言
黄金是典型的状态切换型资产。部分交易日表现为低波动、弱延续与频繁回吐，另一些交易日则在欧洲盘或美盘快速完成区间扩张，并形成单边推进。对于日内交易策略而言，能否在交易日开始之前或盘中早段识别“今天是否会进入高波动 regime”，直接决定了仓位、交易频率和止损结构。

前期研究已经证明，黄金日内 regime 并不只由单一新闻事件决定，而更像美元重定价、跨资产冲击、地缘事件和盘中价格发现共同作用的结果。然而，`v2` 之后仍留下两个问题。第一，是否还能通过引入更贴近黄金市场结构的外部代理变量进一步提高解释力。第二，新增提升中有多少是真实稳定的信息，有多少只是小样本下的表面增益。

本文围绕这两个问题展开扩展研究。一方面，引入 `GLD`、`COMEX` 黄金期货成交、`GVZ` 黄金隐含波动率、`JPY` 避险轮动等开源代理变量，构建 `v3`。另一方面，使用时间序列交叉验证选择 `L2 Logistic` 与 `Ridge` 的正则化强度，构建 `v3r`，检验 `v3` 的提升是否稳健。

## 2. 理论框架与研究假设
### 2.1 美元、收益率与跨资产冲击
黄金在交易层面更接近“对美元和实际利率重定价的放大器”，而非仅仅是一个独立的避险资产。因此，当 `DOLLAR_SHOCK`、收益率冲击与风险资产波动同时出现时，黄金更容易从普通日内波动切换到高波动 regime。

### 2.2 宏观与地缘事件的催化作用
宏观与地缘事件并不会自动转化为黄金高波动日。真正重要的是事件是否通过美元、波动率或周末风险积累转化为可交易的价格冲击。因此，`FED_POLICY`、`GEO_ANY_SHOCK` 与 `WEEKEND_GEO_CARRY` 更应被理解为“催化条件”，而非独立决定变量。

### 2.3 外部代理变量的边际信息
如果黄金日内 regime 还包含一层传统价格变量难以完全吸收的市场结构信息，那么最可能的来源有四类：`GLD` 代表的现货资金流代理，`COMEX` 期货成交量代表的交易活跃度，`GVZ` 代表的黄金隐含波动率，以及 `JPY` 代表的避险轮动强度。`v3` 与 `v3r` 的主要目标，就是检验这些代理是否能在 `v2` 的基础上提供增量解释力。

## 3. 数据、变量与方法
### 3.1 数据来源
本文使用四类数据：

1. 本地 `MT5` 终端中的 `XAUUSD M15` 历史数据。
2. 本地 `MQL5` 原生日历导出数据。
3. 开源 [Wikipedia Current Events Portal](https://en.wikipedia.org/wiki/Portal:Current_events/October_2025) 文本档案，并通过 [MediaWiki Parse API](https://www.mediawiki.org/wiki/API:Parsing_wikitext) 解析后映射至交易日。
4. 开源市场代理数据，包括 `DX-Y.NYB`、`^TNX`、`TIP`、`^VIX`、`CL=F`、`^GSPC` 以及新增的 `GLD`、`GC=F`、`^GVZ`、`JPY=X` 等日频序列。

### 3.2 Regime定义
本文以交易日为单位定义黄金日内 regime：

- `range_ratio`：当日区间相对前 `20` 日中位区间的比值。
- `high_vol_day`：当 `range_ratio >= 1.25` 时，记为高波动日。
- `trend_day`：当 `range_ratio >= 1.25` 且实体占区间比例 `>= 0.55` 时，记为趋势日。
- `regime_score`：将区间扩张与实体占比综合为连续型指标。

长样本中的基线平均 `range_ratio` 为 `1.20`，高波动日占比为 `31.0%`，趋势日占比为 `17.9%`。重叠样本中的对应指标分别为 `1.36`、`35.9%` 与 `19.5%`。

### 3.3 模型层级
本文共比较四代模型：

1. `v1`：价格、时段、跨资产、宏观与地缘的基础因子模型。
2. `v2`：在 `v1` 基础上加入强度分数与伦敦/纽约前两小时微观结构。
3. `v3`：在 `v2` 基础上引入 `GLD`、`COMEX`、`GVZ` 与 `JPY` 等外部代理，并以前向特征选择保留新增变量。
4. `v3r`：固定 `v3` 特征集合，使用时间序列交叉验证选择 `L2 Logistic` 与 `Ridge` 超参数，抑制小样本分离与过拟合。

`v3r` 中的主要正则化强度如下表所示。

| 模型组 | 高波动Logit C | 趋势Logit C | Ridge alpha |
| --- | --- | --- | --- |
| 长样本 解释模型 | 0.30 | 0.10 | 10.00 |
| 重叠样本 解释模型 | 3.00 | 10.00 | 30.00 |
| 长样本 早期模型 | 3.00 | 10.00 | 0.03 |
| 重叠样本 早期模型 | 1.00 | 10.00 | 30.00 |

## 4. 单因子证据
### 4.1 长样本
长样本中，最重要的单因子仍然集中在美元与跨资产冲击，而不是价格压缩。表 1 显示，`DOLLAR_SHOCK`、`DOLLAR_YIELD_CONFLUENCE` 与 `CROSS_ASSET_ANY_SHOCK` 对高波动日概率有稳定正向作用；`PREV_DAY_COMPRESSION` 和 `asia_compression_plus_europe_break` 则呈现负向关系。

| 因子 | 样本日数 | 平均范围比 | 中位范围比 | 范围抬升(%) | 高波动日占比 | 趋势日占比 |
| --- | --- | --- | --- | --- | --- | --- |
| DOLLAR_SHOCK | 62 | 1.58 | 1.25 | 41.84 | 50.0% | 33.9% |
| DOLLAR_YIELD_CONFLUENCE | 16 | 1.57 | 1.44 | 32.76 | 62.5% | 43.8% |
| CROSS_ASSET_ANY_SHOCK | 173 | 1.33 | 1.11 | 25.62 | 38.2% | 23.1% |
| SPX_SHOCK | 60 | 1.43 | 1.28 | 24.59 | 50.0% | 35.0% |
| VIX_SHOCK | 60 | 1.43 | 1.23 | 23.94 | 46.7% | 35.0% |
| OPEN_OUTSIDE_PREV_RANGE | 27 | 1.43 | 1.07 | 21.36 | 40.7% | 11.1% |
| PREV_DAY_COMPRESSION | 95 | 0.96 | 0.93 | -26.78 | 13.7% | 11.6% |
| asia_compression_plus_europe_break | 84 | 0.89 | 0.87 | -32.54 | 13.1% | 9.5% |

![图1 长样本主导因子](C:\Users\WANG PENGBO\Documents\roblox\artifacts_xauusd_regime_factor_research\fullsample_top_factors.png)

### 4.2 重叠样本
叠加宏观日历与地缘事件后，黄金 regime 的结构更接近“美元主导、政策与地缘催化、欧洲盘确认”的模式。表 2 显示，`DOLLAR_SHOCK`、`GEO_ANY_SHOCK`、`WEEKEND_GEO_CARRY` 与 `FED_POLICY` 均具有稳定抬升作用，其中 `WEEKEND_GEO_CARRY` 说明地缘风险常以周末积累、下一交易日释放的方式进入价格。

| 因子 | 类别 | 样本日数 | 平均范围比 | 中位范围比 | 范围抬升(%) | 高波动日占比 | 趋势日占比 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| DOLLAR_SHOCK | 价格/跨资产 | 16 | 2.24 | 1.44 | 82.26 | 62.5% | 31.2% |
| GEO_ANY_SHOCK | 日历/地缘 | 39 | 1.63 | 1.33 | 32.51 | 51.3% | 35.9% |
| GEO_RUSSIA_UKRAINE_SHOCK | 日历/地缘 | 20 | 1.62 | 1.30 | 24.09 | 50.0% | 35.0% |
| WEEKEND_GEO_CARRY | 日历/地缘 | 26 | 1.52 | 1.17 | 15.47 | 46.2% | 30.8% |
| FED_POLICY | 日历/地缘 | 8 | 1.54 | 1.34 | 14.50 | 50.0% | 37.5% |
| US_INFLATION | 日历/地缘 | 14 | 1.54 | 0.92 | 15.88 | 21.4% | 21.4% |
| OPEN_OUTSIDE_PREV_RANGE | 价格/跨资产 | 13 | 1.70 | 1.14 | 29.15 | 46.2% | 7.7% |
| CROSS_ASSET_ANY_SHOCK | 价格/跨资产 | 72 | 1.49 | 1.10 | 26.90 | 38.9% | 22.2% |

![图2 重叠样本主导因子](C:\Users\WANG PENGBO\Documents\roblox\artifacts_xauusd_regime_factor_research\overlap_top_factors.png)

## 5. 模型升级路径：从v1到v3r
为了识别解释力的真实来源，本文将主模型按 `v1 -> v2 -> v3 -> v3r` 的顺序逐级比较。结果如下表所示。

| 指标 | v1 | v2 | v3 | v3r |
| --- | --- | --- | --- | --- |
| 长样本 高波动 AUC | 0.750 | 0.845 | 0.900 | 0.917 |
| 长样本 趋势日 AUC | 0.697 | 0.767 | 0.902 | 0.940 |
| 长样本 RegimeScore 相关 | 0.248 | 0.764 | 0.884 | 0.889 |
| 重叠样本 高波动 AUC | 0.728 | 0.816 | 0.732 | 0.888 |
| 重叠样本 趋势日 AUC | 0.625 | 0.672 | 0.862 | 0.902 |
| 重叠样本 RegimeScore 相关 | 0.453 | 0.776 | 0.890 | 0.871 |

可以看到，`v1 -> v2` 是第一次显著跃迁，说明同日早盘微观结构本身就携带大量 regime 信息；`v2 -> v3` 则证明外部代理变量仍有边际信息，尤其在长样本趋势日与重叠样本的事件环境中更明显；`v3 -> v3r` 的结果最关键，它说明正则化并没有抹掉新增提升，反而在多个指标上进一步改善模型，尤其是重叠样本的 `high_vol AUC` 从 `0.732` 回升至 `0.888`，表明 `v3` 中一部分受分离风险干扰的估计，在正则化后被校正为更稳健的增益。

![图3 v2、v3与v3r AUC比较](C:\Users\WANG PENGBO\Documents\roblox\artifacts_xauusd_regime_factor_research_v3_regularized\v2_v3_v3r_auc.png)
![图4 v2、v3与v3r 相关系数比较](C:\Users\WANG PENGBO\Documents\roblox\artifacts_xauusd_regime_factor_research_v3_regularized\v2_v3_v3r_corr.png)

## 6. 新增外部代理的边际信息
`v3` 被保留下来的新增变量如下表所示。

| 模型组 | 新增代理 | 含义 |
| --- | --- | --- |
| 长样本 解释模型 | gld_abs_z20 | GLD 波动强度代理 |
| 重叠样本 解释模型 | gld_flow_proxy | GLD 波动与成交量结合的资金流代理 |
| 重叠样本 解释模型 | gld_abs_z20 | GLD 波动强度代理 |
| 长样本 早期模型 | gc_volume_ratio20_lag1 | COMEX 黄金期货成交量相对强度(滞后) |
| 长样本 早期模型 | gvz_abs_z20_lag1 | 黄金隐含波动率 GVZ 强度(滞后) |
| 长样本 早期模型 | jpy_ret_lag1 | 日元避险轮动收益(滞后) |
| 重叠样本 早期模型 | gold_vol_credit_intensity_lag1 | 黄金波动率与信用风险耦合强度(滞后) |
| 重叠样本 早期模型 | jpy_ret_lag1 | 日元避险轮动收益(滞后) |

这些结果有三层含义。第一，`GLD` 相关代理在解释模型里最稳定，说明黄金 ETF 的波动与成交强度确实能提供 `v2` 之外的信息。第二，`COMEX` 成交、`GVZ` 与 `JPY` 主要出现在早期模型中，说明它们更像开盘前或欧洲盘早段的辅助先验，而不是全天解释变量。第三，外部代理并没有推翻 `v2` 的微观结构主线，而是与之形成互补。

下表给出 `v3r` 中收缩后仍然最重要的变量。

| 模型 | 变量 | 收缩后系数 |
| --- | --- | --- |
| 长样本 高波动Logit | gld_abs_z20 | 1.526 |
| 长样本 高波动Logit | range_ratio_europe | 0.873 |
| 长样本 高波动Logit | us2h_range_ratio | 0.844 |
| 长样本 高波动Logit | london2h_range_ratio | 0.713 |
| 长样本 高波动Logit | prev_day_range_ratio | 0.391 |
| 长样本 高波动Logit | tnx_abs_z20 | 0.260 |
| 重叠样本 高波动Logit | gld_flow_proxy | 2.132 |
| 重叠样本 高波动Logit | range_ratio_europe | 1.829 |
| 重叠样本 高波动Logit | WEEKEND_GEO_CARRY | 1.172 |
| 重叠样本 高波动Logit | london2h_range_ratio | 1.104 |
| 重叠样本 高波动Logit | gld_abs_z20 | 0.604 |
| 重叠样本 高波动Logit | GEO_MIDDLE_EAST_score_z20_abs | -0.587 |
| 重叠样本 早期高波动Logit | london2h_range_ratio | 1.651 |
| 重叠样本 早期高波动Logit | gold_vol_credit_intensity_lag1 | 0.748 |
| 重叠样本 早期高波动Logit | jpy_ret_lag1 | -0.689 |
| 重叠样本 早期高波动Logit | prev_day_range_ratio | 0.635 |
| 重叠样本 早期高波动Logit | WEEKEND_GEO_CARRY | 0.528 |
| 重叠样本 早期高波动Logit | OPEN_OUTSIDE_PREV_RANGE | -0.407 |

长样本解释模型中，`gld_abs_z20` 的系数最大，说明 `GLD` 波动强度是 `v2` 之外最稳定的新增信息；重叠样本中，`gld_flow_proxy`、`WEEKEND_GEO_CARRY` 和 `range_ratio_europe` 同时占优，说明事件环境下，ETF 代理与地缘 carry 需要由欧洲盘扩张共同确认；重叠样本早期模型中，`gold_vol_credit_intensity_lag1` 和 `jpy_ret_lag1` 被保留下来，说明“黄金隐含波动率与信用风险的共振”以及“避险资金轮动”确实能够在开盘前提供部分先验。

## 7. 可交易性：早期模型的提升与上限
解释模型的提升不等于可交易模型的同步提升。表 5 汇报了早期模型在 `v2`、`v3` 与 `v3r` 下的对比。

| 指标 | v2早期 | v3早期 | v3r早期 |
| --- | --- | --- | --- |
| 长样本 早期高波动 AUC | 0.826 | 0.795 | 0.796 |
| 长样本 早期 RegimeScore 相关 | 0.664 | 0.656 | 0.656 |
| 重叠样本 早期高波动 AUC | 0.664 | 0.728 | 0.736 |
| 重叠样本 早期 RegimeScore 相关 | 0.186 | 0.220 | 0.297 |

结果非常清楚。长样本中，早期模型在 `v2` 已经达到较高水平，`v3` 与 `v3r` 几乎没有进一步提高，说明对于一般性的黄金高波动日，真正难以被开盘前信息捕捉的部分，仍然集中在伦敦前两小时的同日价格发现。相反，重叠样本中的早期模型确实得到改善，`high_vol AUC` 从 `0.664` 升至 `0.736`，`regime_score` 相关从 `0.186` 升至 `0.297`。这意味着在地缘与宏观主导的短样本环境下，`GLD`、`GVZ`、`JPY` 等外部代理有助于增强开盘前判断，但这种增量仍然明显弱于解释模型中的提升。

因此，`v3r` 的最大贡献不是把黄金 regime 变成“完全可提前预测”的问题，而是更精确地划出了边界：哪些部分可以在交易前作为先验概率使用，哪些部分必须等待伦敦盘开盘后的价格确认。

## 8. 讨论与策略含义
### 8.1 为什么正则化能够改善结果
`v3` 中出现的分离警告表明，小样本与强事件冲击下，若直接使用未收缩的 Logit，容易把局部极端样本误当成永久规律。`v3r` 通过时间序列交叉验证选择 `L2` 强度后，既保留了 `GLD`、`COMEX`、`GVZ` 与 `JPY` 等新增代理的主要信息，又显著降低了估计不稳定性。这也是为什么重叠样本的 `high_vol AUC` 在 `v3r` 中反而高于 `v3`。

### 8.2 为什么长样本早期模型几乎不再提升
长样本早期模型在 `v2` 之后就接近平台期，说明黄金普通交易日的大部分 regime 信息，已经被“前一日结构 + 美元/跨资产滞后强度 + 伦敦前两小时范围”解释得差不多。外部代理变量的确有帮助，但其帮助更多体现在事件环境或趋势确认上，而不是把开盘前判断的上限显著抬高。

### 8.3 对EA设计的含义
从 EA 角度看，本文结果并不支持把更多静态宏观标签继续堆进策略，而支持一种两阶段 regime filter：

1. 隔夜阶段：使用前一日结构、周末地缘 carry、美元与跨资产滞后强度，以及 `GLD`/`COMEX`/`GVZ`/`JPY` 的外部代理，给出先验 regime 分数。
2. 伦敦确认阶段：利用伦敦前两小时范围扩张、是否突破前日区间，以及欧洲盘范围强度，对先验分数进行上修或下修。

这一路线与 `v3r` 的结果完全一致：真正稳健的提升，来自“外部代理 + 盘中确认”的结合，而不是单独依赖任何一类信息。

## 9. 结论
本文在 `v2` 研究的基础上，将黄金盘中波动 regime 的建模进一步推进到 `v3` 与 `v3r`。结论可以概括为五点。

第一，美元与跨资产冲击仍然是黄金日内 regime 的基础驱动力，`DOLLAR_SHOCK` 的地位并未被后续模型改变。  
第二，`v2` 通过加入伦敦/纽约前两小时的微观结构，大幅提高了对高波动日和趋势日的解释能力，证明同日价格发现是黄金 regime 的核心组成部分。  
第三，`v3` 新增的 `GLD`、`COMEX`、`GVZ` 与 `JPY` 等外部代理确实存在边际信息，其中 `GLD` 代理在解释模型中最稳定，`COMEX`、`GVZ` 与 `JPY` 更偏向早期可交易信息。  
第四，`v3r` 表明这些新增信息并非表面上的小样本噪声。经过正则化后，长样本与重叠样本中的多数关键指标均优于 `v2`，说明外部代理对黄金 regime 具有真实而稳健的补充作用。  
第五，早期模型的提升仍明显小于解释模型，说明黄金盘中 regime 的一部分本质上属于欧洲盘早段才完成的同日价格发现，不能被开盘前信息完全替代。

因此，若要将本文结论真正写入 `XAUUSD` 交易系统，最合理的路径不是继续堆砌新闻标签，而是采用“隔夜先验 + 伦敦确认”的两阶段架构，并在隔夜先验中加入 `GLD`、`COMEX`、`GVZ` 与 `JPY` 等外部代理。

## 参考文献
1. MediaWiki. *API: Parsing wikitext*. [https://www.mediawiki.org/wiki/API:Parsing_wikitext](https://www.mediawiki.org/wiki/API:Parsing_wikitext)
2. Wikipedia. *Portal: Current events*. [https://en.wikipedia.org/wiki/Portal:Current_events/October_2025](https://en.wikipedia.org/wiki/Portal:Current_events/October_2025)
3. 研究脚本与结果目录：
   [xauusd_regime_factor_research.py](C:\Users\WANG PENGBO\Documents\roblox\xauusd_regime_factor_research.py)
   [xauusd_regime_factor_research_v2.py](C:\Users\WANG PENGBO\Documents\roblox\xauusd_regime_factor_research_v2.py)
   [xauusd_regime_factor_research_v3.py](C:\Users\WANG PENGBO\Documents\roblox\xauusd_regime_factor_research_v3.py)
   [xauusd_regime_factor_research_v3_regularized.py](C:\Users\WANG PENGBO\Documents\roblox\xauusd_regime_factor_research_v3_regularized.py)
   [artifacts_xauusd_regime_factor_research](C:\Users\WANG PENGBO\Documents\roblox\artifacts_xauusd_regime_factor_research)
   [artifacts_xauusd_regime_factor_research_v2](C:\Users\WANG PENGBO\Documents\roblox\artifacts_xauusd_regime_factor_research_v2)
   [artifacts_xauusd_regime_factor_research_v3](C:\Users\WANG PENGBO\Documents\roblox\artifacts_xauusd_regime_factor_research_v3)
   [artifacts_xauusd_regime_factor_research_v3_regularized](C:\Users\WANG PENGBO\Documents\roblox\artifacts_xauusd_regime_factor_research_v3_regularized)
