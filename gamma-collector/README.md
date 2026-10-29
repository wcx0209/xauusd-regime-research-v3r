# GLD Gamma Collector

每小时从 Yahoo Finance 下载 GLD 期权链，用 Black–Scholes Gamma 与未平仓量估算 Gamma Exposure，再把聚合后的关键点位写入 GitHub。公开的 XAU/GLD Gamma Dashboard 会读取 `gamma-data/latest.json`，并用自己的每小时任务把关键点位存入数据库。

同一个工作流也下载 FXY 期权链，将 FXY 行权价按当时的 FXY/USDJPY 比率反向映射成 USDJPY 点位，输出到 `jpy-gamma-data/latest.json`。这是日元ETF代理，不是CME 6J或OTC做市商账本。

## 数据口径

- 标的与期权链：Yahoo Finance 的 `GLD`
- XAU 映射价格：Gold API 的 `XAU/USD` 综合现货价（无需 API Key）
- 利率：`^IRX`，失败时回退到 4%
- Gamma：Black–Scholes 单位 Gamma
- GEX：`Gamma × OI × 100 × Spot² × 1%`
- 符号假设：Call 为正、Put 为负
- 到期范围：未来 90 天内最多 8 个到期日
- 刷新：GitHub Actions 每小时第 47 分钟触发，站点约在整点入库，也支持手动运行

这不是做市商真实持仓。Yahoo 不提供做市商账本、成交方向或逐笔买卖方身份；结果是基于公开期权链和符号假设的风险地图，用于研究和回测，不应单独作为交易指令。

## 本地验证

```bash
python -m pip install -r requirements.txt
python collector.py --dry-run
```

线上工作流只使用 GitHub 自动提供的 `GITHUB_TOKEN` 写回本仓库，不需要额外密钥。`gamma-data/history.csv` 保留每小时记录，可直接用于回测。

