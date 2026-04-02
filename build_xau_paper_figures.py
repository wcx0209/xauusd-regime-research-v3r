from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from xauusd_regime_switching_grid_backtest import (
    build_curve,
    fetch_rates,
    initialize_mt5,
    monthly_pnl,
    prepare_features,
    split_train_forward,
    summarize_trades,
)


ROOT = Path(r"C:\Users\WANG PENGBO\Documents\roblox")
ARTIFACT_DIR = ROOT / "artifacts_xauusd_trend_overlay_second_round"
OUTDIR = ROOT / "report_xau_paper"
TERMINAL_PATH = r"C:\MT5PortableCodex\terminal64.exe"
SYMBOL = "XAUUSD"
TIMEFRAME = "M15"
BARS = 30000
TRAIN_RATIO = 0.70
LOT_SIZE = 0.10


def build_buyhold_curve(df: pd.DataFrame, contract_size: float, lot_size: float) -> tuple[pd.DataFrame, dict[str, float]]:
    entry_price = float(df["open"].iloc[0] + df["spread_price"].iloc[0] * 0.5)
    mark = df["close"] - (df["spread_price"] * 0.5)
    equity = (mark - entry_price) * contract_size * lot_size
    curve = pd.DataFrame({"exit_time": pd.to_datetime(df["time"]), "equity": equity.to_numpy()})
    curve["peak"] = curve["equity"].cummax()
    curve["drawdown"] = curve["equity"] - curve["peak"]
    rolling_peak = np.maximum.accumulate(curve["equity"].to_numpy())
    dd_abs = rolling_peak - curve["equity"].to_numpy()
    metrics = {
        "trades": 1.0,
        "total_pnl": float(curve["equity"].iloc[-1]),
        "profit_factor": float("nan"),
        "max_drawdown_abs": float(dd_abs.max()) if len(dd_abs) else 0.0,
        "max_drawdown": float(curve["drawdown"].min()) if len(curve) else 0.0,
    }
    return curve, metrics


def plot_equity_compare(strategy_curve: pd.DataFrame, buyhold_curve: pd.DataFrame, split_time: pd.Timestamp, path: Path, title: str) -> None:
    fig, ax = plt.subplots(figsize=(12, 5.6))
    ax.plot(strategy_curve["exit_time"], strategy_curve["equity"], label="Strategy", color="#0f766e", linewidth=2.1)
    ax.plot(buyhold_curve["exit_time"], buyhold_curve["equity"], label="Buy & Hold", color="#b45309", linewidth=1.8)
    ax.axvline(split_time, color="#444444", linestyle="--", linewidth=1.2, label="Forward split")
    ax.axhline(0.0, color="#9ca3af", linewidth=0.8)
    ax.set_title(title)
    ax.set_ylabel("Net PnL (USD, 0.10 lot)")
    ax.grid(alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def plot_drawdown_compare(strategy_curve: pd.DataFrame, buyhold_curve: pd.DataFrame, split_time: pd.Timestamp, path: Path, title: str) -> None:
    fig, ax = plt.subplots(figsize=(12, 4.8))
    ax.plot(strategy_curve["exit_time"], strategy_curve["drawdown"], label="Strategy", color="#0f766e", linewidth=2.1)
    ax.plot(buyhold_curve["exit_time"], buyhold_curve["drawdown"], label="Buy & Hold", color="#b45309", linewidth=1.8)
    ax.axvline(split_time, color="#444444", linestyle="--", linewidth=1.2)
    ax.set_title(title)
    ax.set_ylabel("Drawdown")
    ax.grid(alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def plot_monthly(strategy_trades: pd.DataFrame, buyhold_curve: pd.DataFrame, path: Path) -> None:
    strategy_monthly = monthly_pnl(strategy_trades)
    buyhold = buyhold_curve.copy()
    buyhold["month"] = pd.to_datetime(buyhold["exit_time"]).dt.to_period("M").dt.to_timestamp()
    buyhold_monthly = buyhold.groupby("month")["equity"].last().diff().fillna(buyhold.groupby("month")["equity"].last())
    months = sorted(set(strategy_monthly.index).union(set(buyhold_monthly.index)))
    strategy_vals = [float(strategy_monthly.get(m, 0.0)) for m in months]
    buyhold_vals = [float(buyhold_monthly.get(m, 0.0)) for m in months]

    x = np.arange(len(months))
    width = 0.4
    fig, ax = plt.subplots(figsize=(12, 4.8))
    ax.bar(x - width / 2, strategy_vals, width=width, label="Strategy", color="#0f766e")
    ax.bar(x + width / 2, buyhold_vals, width=width, label="Buy & Hold", color="#b45309")
    ax.set_xticks(x)
    ax.set_xticklabels([pd.Timestamp(m).strftime("%Y-%m") for m in months], rotation=45, ha="right")
    ax.set_title("Monthly PnL Comparison")
    ax.set_ylabel("PnL")
    ax.grid(axis="y", alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def write_metrics(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    OUTDIR.mkdir(parents=True, exist_ok=True)

    train_trades = pd.read_csv(ARTIFACT_DIR / "recommended_train_trades.csv")
    forward_trades = pd.read_csv(ARTIFACT_DIR / "recommended_forward_trades.csv")
    train_trades["exit_time"] = pd.to_datetime(train_trades["exit_time"])
    forward_trades["exit_time"] = pd.to_datetime(forward_trades["exit_time"])

    train_curve = build_curve(train_trades, "Train", start_equity=0.0)
    train_end_equity = float(train_curve["equity"].iloc[-1]) if not train_curve.empty else 0.0
    forward_curve = build_curve(forward_trades, "Forward", start_equity=train_end_equity)
    strategy_curve = pd.concat([train_curve, forward_curve], ignore_index=True)

    initialize_mt5(TERMINAL_PATH)
    try:
        raw_bars, point, contract_size = fetch_rates(SYMBOL, TIMEFRAME, BARS)
    finally:
        import MetaTrader5 as mt5

        mt5.shutdown()

    bars = prepare_features(raw_bars)
    train_df, forward_df = split_train_forward(bars, TRAIN_RATIO)
    split_time = pd.to_datetime(forward_df["time"].iloc[0])

    buyhold_train_curve, buyhold_train_metrics = build_buyhold_curve(train_df.reset_index(drop=True), contract_size, LOT_SIZE)
    buyhold_forward_curve_local, buyhold_forward_metrics = build_buyhold_curve(forward_df.reset_index(drop=True), contract_size, LOT_SIZE)

    buyhold_full_df = pd.concat([train_df, forward_df], ignore_index=True)
    buyhold_full_curve, buyhold_full_metrics = build_buyhold_curve(buyhold_full_df, contract_size, LOT_SIZE)
    buyhold_full_curve["segment"] = np.where(pd.to_datetime(buyhold_full_curve["exit_time"]) < split_time, "Train", "Forward")

    train_metrics = summarize_trades(train_trades.to_dict("records"), max_units=2)
    forward_metrics = summarize_trades(forward_trades.to_dict("records"), max_units=2)
    full_metrics = summarize_trades(pd.concat([train_trades, forward_trades], ignore_index=True).to_dict("records"), max_units=2)

    plot_equity_compare(strategy_curve, buyhold_full_curve, split_time, OUTDIR / "xau_strategy_vs_buyhold_equity_full.png", "XAUUSD M15: Strategy vs Buy & Hold (Full Sample)")
    plot_drawdown_compare(strategy_curve, buyhold_full_curve, split_time, OUTDIR / "xau_strategy_vs_buyhold_drawdown_full.png", "XAUUSD M15: Drawdown Comparison (Full Sample)")

    strategy_forward_curve = forward_curve.copy()
    strategy_forward_curve["exit_time"] = pd.to_datetime(strategy_forward_curve["exit_time"])
    strategy_forward_curve["drawdown"] = strategy_forward_curve["drawdown"] - strategy_forward_curve["drawdown"].iloc[0]
    buyhold_forward_curve = buyhold_forward_curve_local.copy()
    buyhold_forward_curve["segment"] = "Forward"
    plot_equity_compare(
        strategy_forward_curve.rename(columns={"exit_time": "exit_time", "equity": "equity"}),
        buyhold_forward_curve.rename(columns={"exit_time": "exit_time", "equity": "equity"}),
        split_time,
        OUTDIR / "xau_strategy_vs_buyhold_equity_forward.png",
        "XAUUSD M15: Strategy vs Buy & Hold (Forward Window)",
    )
    plot_monthly(pd.concat([train_trades, forward_trades], ignore_index=True), buyhold_full_curve, OUTDIR / "xau_strategy_vs_buyhold_monthly.png")

    rows = [
        {"window": "train", "mode": "strategy", "net_profit": train_metrics["total_pnl"], "profit_factor": train_metrics["profit_factor"], "max_drawdown": abs(train_metrics["max_drawdown"]), "trades": train_metrics["trades"]},
        {"window": "train", "mode": "buy_hold", "net_profit": buyhold_train_metrics["total_pnl"], "profit_factor": float("nan"), "max_drawdown": buyhold_train_metrics["max_drawdown_abs"], "trades": 1},
        {"window": "forward", "mode": "strategy", "net_profit": forward_metrics["total_pnl"], "profit_factor": forward_metrics["profit_factor"], "max_drawdown": abs(forward_metrics["max_drawdown"]), "trades": forward_metrics["trades"]},
        {"window": "forward", "mode": "buy_hold", "net_profit": buyhold_forward_metrics["total_pnl"], "profit_factor": float("nan"), "max_drawdown": buyhold_forward_metrics["max_drawdown_abs"], "trades": 1},
        {"window": "full", "mode": "strategy", "net_profit": full_metrics["total_pnl"], "profit_factor": full_metrics["profit_factor"], "max_drawdown": abs(full_metrics["max_drawdown"]), "trades": full_metrics["trades"]},
        {"window": "full", "mode": "buy_hold", "net_profit": buyhold_full_metrics["total_pnl"], "profit_factor": float("nan"), "max_drawdown": buyhold_full_metrics["max_drawdown_abs"], "trades": 1},
    ]
    write_metrics(OUTDIR / "comparison_metrics.csv", rows)

    summary = [
        "# XAU Paper Figures",
        "",
        f"- Train strategy: net={train_metrics['total_pnl']:.2f}, pf={train_metrics['profit_factor']:.2f}, dd={abs(train_metrics['max_drawdown']):.2f}",
        f"- Train buy_hold: net={buyhold_train_metrics['total_pnl']:.2f}, dd={buyhold_train_metrics['max_drawdown_abs']:.2f}",
        f"- Forward strategy: net={forward_metrics['total_pnl']:.2f}, pf={forward_metrics['profit_factor']:.2f}, dd={abs(forward_metrics['max_drawdown']):.2f}",
        f"- Forward buy_hold: net={buyhold_forward_metrics['total_pnl']:.2f}, dd={buyhold_forward_metrics['max_drawdown_abs']:.2f}",
        f"- Full strategy: net={full_metrics['total_pnl']:.2f}, pf={full_metrics['profit_factor']:.2f}, dd={abs(full_metrics['max_drawdown']):.2f}",
        f"- Full buy_hold: net={buyhold_full_metrics['total_pnl']:.2f}, dd={buyhold_full_metrics['max_drawdown_abs']:.2f}",
    ]
    (OUTDIR / "summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
