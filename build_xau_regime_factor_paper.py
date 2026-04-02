from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent
ART_V1 = ROOT / "artifacts_xauusd_regime_factor_research"
ART_V2 = ROOT / "artifacts_xauusd_regime_factor_research_v2"
ART_V3 = ROOT / "artifacts_xauusd_regime_factor_research_v3"
ART_V3R = ROOT / "artifacts_xauusd_regime_factor_research_v3_regularized"
PAPER_PATH = ROOT / "XAUUSD盘中波动Regime驱动因素研究_基于MT5与开源多因子数据的实证分析.md"


def load_csv(base: Path, name: str) -> pd.DataFrame:
    return pd.read_csv(base / name)


def fmt_num(value: float, digits: int = 2) -> str:
    return f"{float(value):.{digits}f}"


def fmt_pct(value: float) -> str:
    return f"{float(value) * 100:.1f}%"


def keep_rows(df: pd.DataFrame, labels: list[str], key: str = "label") -> pd.DataFrame:
    lookup = {str(row[key]): row for _, row in df.iterrows()}
    rows = [lookup[label] for label in labels if label in lookup]
    return pd.DataFrame(rows)


def to_markdown_table(df: pd.DataFrame) -> str:
    if df.empty:
        return ""
    headers = list(df.columns)
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for _, row in df.iterrows():
        cells = [str(row[col]) for col in headers]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def build_single_factor_tables() -> tuple[str, str]:
    full_rank = load_csv(ART_V1, "fullsample_factor_rank.csv")
    overlap_rank = load_csv(ART_V1, "overlap_factor_rank.csv")

    full_labels = [
        "DOLLAR_SHOCK",
        "DOLLAR_YIELD_CONFLUENCE",
        "CROSS_ASSET_ANY_SHOCK",
        "SPX_SHOCK",
        "VIX_SHOCK",
        "OPEN_OUTSIDE_PREV_RANGE",
        "PREV_DAY_COMPRESSION",
        "asia_compression_plus_europe_break",
    ]
    overlap_labels = [
        "DOLLAR_SHOCK",
        "GEO_ANY_SHOCK",
        "GEO_RUSSIA_UKRAINE_SHOCK",
        "WEEKEND_GEO_CARRY",
        "FED_POLICY",
        "US_INFLATION",
        "OPEN_OUTSIDE_PREV_RANGE",
        "CROSS_ASSET_ANY_SHOCK",
    ]

    full = keep_rows(full_rank, full_labels).copy()
    full = full.rename(
        columns={
            "label": "因子",
            "event_days": "样本日数",
            "avg_range_ratio": "平均范围比",
            "median_range_ratio": "中位范围比",
            "range_lift_pct": "范围抬升(%)",
            "high_vol_rate": "高波动日占比",
            "trend_day_rate": "趋势日占比",
        }
    )[["因子", "样本日数", "平均范围比", "中位范围比", "范围抬升(%)", "高波动日占比", "趋势日占比"]]
    for col in ["平均范围比", "中位范围比", "范围抬升(%)"]:
        full[col] = full[col].map(lambda x: fmt_num(x))
    for col in ["高波动日占比", "趋势日占比"]:
        full[col] = full[col].map(fmt_pct)

    overlap = keep_rows(overlap_rank, overlap_labels).copy()
    overlap = overlap.rename(
        columns={
            "label": "因子",
            "source_group": "类别",
            "event_days": "样本日数",
            "avg_range_ratio": "平均范围比",
            "median_range_ratio": "中位范围比",
            "range_lift_pct": "范围抬升(%)",
            "high_vol_rate": "高波动日占比",
            "trend_day_rate": "趋势日占比",
        }
    )[["因子", "类别", "样本日数", "平均范围比", "中位范围比", "范围抬升(%)", "高波动日占比", "趋势日占比"]]
    overlap["类别"] = overlap["类别"].replace({"price_cross_asset": "价格/跨资产", "calendar_geo": "日历/地缘"})
    for col in ["平均范围比", "中位范围比", "范围抬升(%)"]:
        overlap[col] = overlap[col].map(lambda x: fmt_num(x))
    for col in ["高波动日占比", "趋势日占比"]:
        overlap[col] = overlap[col].map(fmt_pct)

    return to_markdown_table(full), to_markdown_table(overlap)


def build_progression_table() -> str:
    comp_v12 = load_csv(ART_V2, "v1_vs_v2_model_comparison.csv")
    comp_v23 = load_csv(ART_V3, "v2_vs_v3_model_comparison.csv")
    comp_v23r = load_csv(ART_V3R, "v2_v3_v3r_model_comparison.csv")

    rows = []
    label_map = {
        "full_high_vol_auc": "长样本 高波动 AUC",
        "full_trend_auc": "长样本 趋势日 AUC",
        "full_regime_corr": "长样本 RegimeScore 相关",
        "overlap_high_vol_auc": "重叠样本 高波动 AUC",
        "overlap_trend_auc": "重叠样本 趋势日 AUC",
        "overlap_regime_corr": "重叠样本 RegimeScore 相关",
    }
    v1_lookup = {str(row["label"]): row for _, row in comp_v12.iterrows()}
    v3_lookup = {str(row["label"]): row for _, row in comp_v23.iterrows()}
    v3r_lookup = {str(row["label"]): row for _, row in comp_v23r.iterrows()}

    for label in label_map:
        rows.append(
            {
                "指标": label_map[label],
                "v1": fmt_num(v1_lookup[label]["metric_v1"], 3),
                "v2": fmt_num(v1_lookup[label]["metric_v2"], 3),
                "v3": fmt_num(v3_lookup[label]["metric_v3"], 3),
                "v3r": fmt_num(v3r_lookup[label]["metric_v3r"], 3),
            }
        )
    return to_markdown_table(pd.DataFrame(rows))


def build_early_table() -> str:
    early_v2 = load_csv(ART_V2, "v2_early_model_comparison.csv")
    early_v3r = load_csv(ART_V3R, "v2_v3_v3r_early_model_comparison.csv")

    rows = []
    label_map = {
        "full_early_high_vol_auc": "长样本 早期高波动 AUC",
        "full_early_regime_corr": "长样本 早期 RegimeScore 相关",
        "overlap_early_high_vol_auc": "重叠样本 早期高波动 AUC",
        "overlap_early_regime_corr": "重叠样本 早期 RegimeScore 相关",
    }
    v2_lookup = {str(row["label"]): row for _, row in early_v2.iterrows()}
    v3r_lookup = {str(row["label"]): row for _, row in early_v3r.iterrows()}
    for label in label_map:
        rows.append(
            {
                "指标": label_map[label],
                "v2早期": fmt_num(v2_lookup[label]["metric_v2_early"], 3),
                "v3早期": fmt_num(v3r_lookup[label]["metric_v3"], 3),
                "v3r早期": fmt_num(v3r_lookup[label]["metric_v3r"], 3),
            }
        )
    return to_markdown_table(pd.DataFrame(rows))


def build_external_addition_table() -> str:
    selected = load_csv(ART_V3, "selected_features_v3.csv")
    mapping = {
        "gld_abs_z20": "GLD 波动强度代理",
        "gld_flow_proxy": "GLD 波动与成交量结合的资金流代理",
        "gc_volume_ratio20_lag1": "COMEX 黄金期货成交量相对强度(滞后)",
        "gvz_abs_z20_lag1": "黄金隐含波动率 GVZ 强度(滞后)",
        "jpy_ret_lag1": "日元避险轮动收益(滞后)",
        "gold_vol_credit_intensity_lag1": "黄金波动率与信用风险耦合强度(滞后)",
    }
    base_sets = {
        "full_explain": {
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
        },
        "overlap_explain": {
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
        },
        "full_early": {
            "prev_day_range_ratio",
            "min_prev_extreme_dist_norm",
            "OPEN_OUTSIDE_PREV_RANGE",
            "london2h_range_ratio",
            "london2h_break_prevday",
            "dxy_abs_z20_lag1",
            "tnx_abs_z20_lag1",
            "vix_abs_z20_lag1",
            "oil_abs_z20_lag1",
        },
        "overlap_early": {
            "WEEKEND_GEO_CARRY",
            "prev_day_range_ratio",
            "OPEN_OUTSIDE_PREV_RANGE",
            "london2h_range_ratio",
            "london2h_break_prevday",
            "dxy_abs_z20_lag1",
            "vix_abs_z20_lag1",
            "geo_total_score_z20_abs_lag1",
        },
    }
    group_map = {
        "full_explain": "长样本 解释模型",
        "overlap_explain": "重叠样本 解释模型",
        "full_early": "长样本 早期模型",
        "overlap_early": "重叠样本 早期模型",
    }

    rows = []
    for _, row in selected.iterrows():
        model_group = str(row["model_group"])
        features = [item for item in str(row["selected_features"]).split(",") if item]
        additions = [item for item in features if item not in base_sets[model_group]]
        for item in additions:
            rows.append(
                {
                    "模型组": group_map[model_group],
                    "新增代理": item,
                    "含义": mapping.get(item, item),
                }
            )
    return to_markdown_table(pd.DataFrame(rows))


def build_v3r_driver_table() -> str:
    sources = [
        (ART_V3R, "fullsample_model_coefficients_v3r.csv", "fullsample_high_vol_logit_v3r", "长样本 高波动Logit"),
        (ART_V3R, "overlap_model_coefficients_v3r.csv", "overlap_high_vol_logit_v3r", "重叠样本 高波动Logit"),
        (ART_V3R, "overlap_early_model_coefficients_v3r.csv", "overlap_early_high_vol_logit_v3r", "重叠样本 早期高波动Logit"),
    ]
    rows = []
    for base, name, model, label in sources:
        df = load_csv(base, name)
        subset = df.loc[df["model"] == model].copy()
        subset = subset.reindex(subset["coef"].abs().sort_values(ascending=False).index).head(6)
        for _, row in subset.iterrows():
            rows.append(
                {
                    "模型": label,
                    "变量": row["feature"],
                    "收缩后系数": fmt_num(row["coef"], 3),
                }
            )
    return to_markdown_table(pd.DataFrame(rows))


def build_regularization_table() -> str:
    files = [
        ("长样本 解释模型", load_csv(ART_V3R, "fullsample_model_summary_v3r.csv")),
        ("重叠样本 解释模型", load_csv(ART_V3R, "overlap_model_summary_v3r.csv")),
        ("长样本 早期模型", load_csv(ART_V3R, "fullsample_early_model_summary_v3r.csv")),
        ("重叠样本 早期模型", load_csv(ART_V3R, "overlap_early_model_summary_v3r.csv")),
    ]
    rows = []
    for label, df in files:
        high = df.loc[df["model"].str.contains("high_vol"), "hyperparam"].iloc[0]
        trend = df.loc[df["model"].str.contains("trend_day"), "hyperparam"].iloc[0]
        regime = df.loc[df["model"].str.contains("regime_score"), "hyperparam"].iloc[0]
        rows.append(
            {
                "模型组": label,
                "高波动Logit C": fmt_num(high, 2),
                "趋势Logit C": fmt_num(trend, 2),
                "Ridge alpha": fmt_num(regime, 2),
            }
        )
    return to_markdown_table(pd.DataFrame(rows))


def main() -> None:
    full_dataset = load_csv(ART_V1, "xau_regime_full_dataset.csv")
    overlap_dataset = load_csv(ART_V1, "xau_regime_overlap_dataset.csv")

    full_table, overlap_table = build_single_factor_tables()
    progression_table = build_progression_table()
    early_table = build_early_table()
    external_addition_table = build_external_addition_table()
    v3r_driver_table = build_v3r_driver_table()
    regularization_table = build_regularization_table()

    baseline_full_range = float(full_dataset["range_ratio"].dropna().mean())
    baseline_full_hv = float(full_dataset["high_vol_day"].mean())
    baseline_full_trend = float(full_dataset["trend_day"].mean())
    baseline_overlap_range = float(overlap_dataset["range_ratio"].dropna().mean())
    baseline_overlap_hv = float(overlap_dataset["high_vol_day"].mean())
    baseline_overlap_trend = float(overlap_dataset["trend_day"].mean())

    md = f"""# XAUUSD盘中波动Regime的决定因素、可交易性与正则化扩展
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

长样本中的基线平均 `range_ratio` 为 `{fmt_num(baseline_full_range)}`，高波动日占比为 `{fmt_pct(baseline_full_hv)}`，趋势日占比为 `{fmt_pct(baseline_full_trend)}`。重叠样本中的对应指标分别为 `{fmt_num(baseline_overlap_range)}`、`{fmt_pct(baseline_overlap_hv)}` 与 `{fmt_pct(baseline_overlap_trend)}`。

### 3.3 模型层级
本文共比较四代模型：

1. `v1`：价格、时段、跨资产、宏观与地缘的基础因子模型。
2. `v2`：在 `v1` 基础上加入强度分数与伦敦/纽约前两小时微观结构。
3. `v3`：在 `v2` 基础上引入 `GLD`、`COMEX`、`GVZ` 与 `JPY` 等外部代理，并以前向特征选择保留新增变量。
4. `v3r`：固定 `v3` 特征集合，使用时间序列交叉验证选择 `L2 Logistic` 与 `Ridge` 超参数，抑制小样本分离与过拟合。

`v3r` 中的主要正则化强度如下表所示。

{regularization_table}

## 4. 单因子证据
### 4.1 长样本
长样本中，最重要的单因子仍然集中在美元与跨资产冲击，而不是价格压缩。表 1 显示，`DOLLAR_SHOCK`、`DOLLAR_YIELD_CONFLUENCE` 与 `CROSS_ASSET_ANY_SHOCK` 对高波动日概率有稳定正向作用；`PREV_DAY_COMPRESSION` 和 `asia_compression_plus_europe_break` 则呈现负向关系。

{full_table}

![图1 长样本主导因子]({ART_V1 / 'fullsample_top_factors.png'})

### 4.2 重叠样本
叠加宏观日历与地缘事件后，黄金 regime 的结构更接近“美元主导、政策与地缘催化、欧洲盘确认”的模式。表 2 显示，`DOLLAR_SHOCK`、`GEO_ANY_SHOCK`、`WEEKEND_GEO_CARRY` 与 `FED_POLICY` 均具有稳定抬升作用，其中 `WEEKEND_GEO_CARRY` 说明地缘风险常以周末积累、下一交易日释放的方式进入价格。

{overlap_table}

![图2 重叠样本主导因子]({ART_V1 / 'overlap_top_factors.png'})

## 5. 模型升级路径：从v1到v3r
为了识别解释力的真实来源，本文将主模型按 `v1 -> v2 -> v3 -> v3r` 的顺序逐级比较。结果如下表所示。

{progression_table}

可以看到，`v1 -> v2` 是第一次显著跃迁，说明同日早盘微观结构本身就携带大量 regime 信息；`v2 -> v3` 则证明外部代理变量仍有边际信息，尤其在长样本趋势日与重叠样本的事件环境中更明显；`v3 -> v3r` 的结果最关键，它说明正则化并没有抹掉新增提升，反而在多个指标上进一步改善模型，尤其是重叠样本的 `high_vol AUC` 从 `0.732` 回升至 `0.888`，表明 `v3` 中一部分受分离风险干扰的估计，在正则化后被校正为更稳健的增益。

![图3 v2、v3与v3r AUC比较]({ART_V3R / 'v2_v3_v3r_auc.png'})
![图4 v2、v3与v3r 相关系数比较]({ART_V3R / 'v2_v3_v3r_corr.png'})

## 6. 新增外部代理的边际信息
`v3` 被保留下来的新增变量如下表所示。

{external_addition_table}

这些结果有三层含义。第一，`GLD` 相关代理在解释模型里最稳定，说明黄金 ETF 的波动与成交强度确实能提供 `v2` 之外的信息。第二，`COMEX` 成交、`GVZ` 与 `JPY` 主要出现在早期模型中，说明它们更像开盘前或欧洲盘早段的辅助先验，而不是全天解释变量。第三，外部代理并没有推翻 `v2` 的微观结构主线，而是与之形成互补。

下表给出 `v3r` 中收缩后仍然最重要的变量。

{v3r_driver_table}

长样本解释模型中，`gld_abs_z20` 的系数最大，说明 `GLD` 波动强度是 `v2` 之外最稳定的新增信息；重叠样本中，`gld_flow_proxy`、`WEEKEND_GEO_CARRY` 和 `range_ratio_europe` 同时占优，说明事件环境下，ETF 代理与地缘 carry 需要由欧洲盘扩张共同确认；重叠样本早期模型中，`gold_vol_credit_intensity_lag1` 和 `jpy_ret_lag1` 被保留下来，说明“黄金隐含波动率与信用风险的共振”以及“避险资金轮动”确实能够在开盘前提供部分先验。

## 7. 可交易性：早期模型的提升与上限
解释模型的提升不等于可交易模型的同步提升。表 5 汇报了早期模型在 `v2`、`v3` 与 `v3r` 下的对比。

{early_table}

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
   [xauusd_regime_factor_research.py]({ROOT / 'xauusd_regime_factor_research.py'})
   [xauusd_regime_factor_research_v2.py]({ROOT / 'xauusd_regime_factor_research_v2.py'})
   [xauusd_regime_factor_research_v3.py]({ROOT / 'xauusd_regime_factor_research_v3.py'})
   [xauusd_regime_factor_research_v3_regularized.py]({ROOT / 'xauusd_regime_factor_research_v3_regularized.py'})
   [artifacts_xauusd_regime_factor_research]({ART_V1})
   [artifacts_xauusd_regime_factor_research_v2]({ART_V2})
   [artifacts_xauusd_regime_factor_research_v3]({ART_V3})
   [artifacts_xauusd_regime_factor_research_v3_regularized]({ART_V3R})
"""
    PAPER_PATH.write_text(md, encoding="utf-8")
    print(f"Saved paper markdown: {PAPER_PATH}")


if __name__ == "__main__":
    main()
