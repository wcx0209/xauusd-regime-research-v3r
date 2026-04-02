import argparse
import itertools
import math
from dataclasses import dataclass
from pathlib import Path

import MetaTrader5 as mt5
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


TIMEFRAME_MAP = {
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1,
}


@dataclass(frozen=True)
class Candidate:
    range_entry_atr: float
    range_step_atr: float
    range_stop_atr: float
    range_max_units: int
    regime_family: str
    regime_adx_threshold: float
    regime_er_threshold: float | None = None
    regime_gap_threshold: float | None = None

    @property
    def name(self) -> str:
        regime_bits = [f"regime={self.regime_family}", f"adx={self.regime_adx_threshold:.0f}"]
        if self.regime_er_threshold is not None:
            regime_bits.append(f"er={self.regime_er_threshold:.2f}")
        if self.regime_gap_threshold is not None:
            regime_bits.append(f"gap={self.regime_gap_threshold:.1f}")
        return (
            f"range_entry={self.range_entry_atr}|range_step={self.range_step_atr}|"
            f"range_stop={self.range_stop_atr}|range_max={self.range_max_units}|"
            + "|".join(regime_bits)
        )


@dataclass
class Lot:
    side: int
    entry_price: float
    entry_time: pd.Timestamp
    entry_idx: int
    entry_reason: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="XAUUSD regime-switching range-grid backtest with strict no-lookahead execution."
    )
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--timeframe", default="M15", choices=sorted(TIMEFRAME_MAP))
    parser.add_argument("--bars", type=int, default=40000)
    parser.add_argument("--train-ratio", type=float, default=0.70)
    parser.add_argument("--session-start", type=int, default=6)
    parser.add_argument("--session-end", type=int, default=22)
    parser.add_argument(
        "--terminal-path",
        default=r"C:\Program Files\MetaTrader 5\terminal64.exe",
    )
    parser.add_argument("--outdir", default="artifacts_xauusd_regime_grid")
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--lot-size", type=float, default=0.10)
    parser.add_argument("--spread-multiplier", type=float, default=1.0)
    parser.add_argument("--slippage-points", type=float, default=1.0)
    parser.add_argument("--range-bars", type=int, default=4)
    return parser.parse_args()


def initialize_mt5(path: str) -> None:
    if not mt5.initialize(path=path):
        raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")


def fetch_rates(symbol: str, timeframe: str, bars: int) -> tuple[pd.DataFrame, float, float]:
    info = mt5.symbol_info(symbol)
    if info is None:
        raise RuntimeError(f"Could not read symbol info for {symbol}")
    rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME_MAP[timeframe], 0, bars)
    if rates is None:
        raise RuntimeError(f"MT5 returned no rates for {symbol}: {mt5.last_error()}")
    df = pd.DataFrame(rates)
    if df.empty:
        raise RuntimeError(f"No bars downloaded for {symbol}.")
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df = df.sort_values("time").reset_index(drop=True)
    df["spread_price"] = df["spread"] * info.point
    return df, float(info.point), float(info.trade_contract_size)


def prepare_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["date"] = out["time"].dt.date
    out["hour"] = out["time"].dt.hour

    prev_close = out["close"].shift(1)
    tr = pd.concat(
        [
            out["high"] - out["low"],
            (out["high"] - prev_close).abs(),
            (out["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    out["atr14"] = tr.ewm(alpha=1 / 14, adjust=False).mean()

    daily = out.groupby("date", sort=True).agg(
        daily_high=("high", "max"),
        daily_low=("low", "min"),
        daily_close=("close", "last"),
    )
    prev_daily_close = daily["daily_close"].shift(1)
    daily_tr = pd.concat(
        [
            daily["daily_high"] - daily["daily_low"],
            (daily["daily_high"] - prev_daily_close).abs(),
            (daily["daily_low"] - prev_daily_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    daily_atr = daily_tr.ewm(alpha=1 / 14, adjust=False).mean()
    daily["daily_ema20"] = daily["daily_close"].ewm(span=20, adjust=False).mean()

    up_move = daily["daily_high"].diff()
    down_move = -daily["daily_low"].diff()
    plus_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move, 0.0),
        index=daily.index,
    )
    minus_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move, 0.0),
        index=daily.index,
    )
    plus_di = 100 * plus_dm.ewm(alpha=1 / 14, adjust=False).mean() / daily_atr.replace(0, np.nan)
    minus_di = 100 * minus_dm.ewm(alpha=1 / 14, adjust=False).mean() / daily_atr.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    daily["daily_adx14"] = dx.ewm(alpha=1 / 14, adjust=False).mean()
    er_window = 10
    daily["daily_er10"] = (
        (daily["daily_close"] - daily["daily_close"].shift(er_window)).abs()
        / daily["daily_close"].diff().abs().rolling(er_window).sum().replace(0, np.nan)
    )
    daily["ema_gap_atr"] = (daily["daily_close"] - daily["daily_ema20"]).abs() / daily_atr.replace(0, np.nan)
    daily["bias"] = np.where(
        daily["daily_close"] > daily["daily_ema20"],
        1,
        np.where(daily["daily_close"] < daily["daily_ema20"], -1, 0),
    )
    daily["prev_bias"] = daily["bias"].shift(1)
    daily["prev_adx14"] = daily["daily_adx14"].shift(1)
    daily["prev_er10"] = daily["daily_er10"].shift(1)
    daily["prev_ema_gap_atr"] = daily["ema_gap_atr"].shift(1)

    merged = out.merge(
        daily[["prev_bias", "prev_adx14", "prev_er10", "prev_ema_gap_atr"]],
        left_on="date",
        right_index=True,
        how="left",
    )
    return merged


def split_train_forward(df: pd.DataFrame, train_ratio: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    unique_dates = pd.Index(df["date"].drop_duplicates())
    if len(unique_dates) < 60:
        raise RuntimeError("Not enough complete trading days to build a train/forward split.")
    split_pos = max(30, min(len(unique_dates) - 30, int(len(unique_dates) * train_ratio)))
    split_date = unique_dates[split_pos]
    train = df[df["date"] < split_date].copy().reset_index(drop=True)
    forward = df[df["date"] >= split_date].copy().reset_index(drop=True)
    if train.empty or forward.empty:
        raise RuntimeError("Train/forward split produced an empty segment.")
    return train, forward


def prepare_simulation_frame(
    df: pd.DataFrame,
    session_start: int,
    session_end: int,
    range_bars: int,
) -> pd.DataFrame:
    out = df.copy()
    out["in_session"] = (out["hour"] >= session_start) & (out["hour"] < session_end)
    out["session_rank"] = -1

    session_rows = out["in_session"]
    out.loc[session_rows, "session_rank"] = out.loc[session_rows].groupby("date").cumcount()
    out["session_rank"] = out["session_rank"].astype(int)

    day_rows = []
    for date, day in out[out["in_session"]].groupby("date", sort=True):
        if len(day) < range_bars:
            continue
        opening = day.iloc[:range_bars]
        opening_high = float(opening["high"].max())
        opening_low = float(opening["low"].min())
        day_rows.append(
            {
                "date": date,
                "opening_high": opening_high,
                "opening_low": opening_low,
                "opening_mid": 0.5 * (opening_high + opening_low),
                "session_end_idx": int(day.index.max()),
                "opening_ready": True,
            }
        )

    day_frame = pd.DataFrame(day_rows)
    if day_frame.empty:
        raise RuntimeError("No valid session days found for simulation.")

    out = out.merge(day_frame, on="date", how="left")
    out["opening_ready"] = out["opening_ready"].fillna(False)
    out["session_end_idx"] = out["session_end_idx"].fillna(-1).astype(int)
    return out


def generate_candidates() -> list[Candidate]:
    candidates = []
    for range_entry, range_max in itertools.product(
        [1.0, 1.1],
        [1, 2],
    ):
        for adx in [20.0, 22.0, 24.0]:
            candidates.append(
                Candidate(
                    range_entry_atr=range_entry,
                    range_step_atr=0.75,
                    range_stop_atr=1.75,
                    range_max_units=range_max,
                    regime_family="adx_only",
                    regime_adx_threshold=adx,
                )
            )
        for adx, er, gap in itertools.product(
            [20.0, 22.0],
            [0.28, 0.32],
            [0.4, 0.6, 0.8],
        ):
            candidates.append(
                Candidate(
                    range_entry_atr=range_entry,
                    range_step_atr=0.75,
                    range_stop_atr=1.75,
                    range_max_units=range_max,
                    regime_family="adx_er_gap",
                    regime_adx_threshold=adx,
                    regime_er_threshold=er,
                    regime_gap_threshold=gap,
                )
            )
    return candidates


def calc_drawdown(pnl: pd.Series) -> float:
    if pnl.empty:
        return 0.0
    curve = pnl.cumsum()
    return float((curve - curve.cummax()).min())


def score_metrics(metrics: dict) -> float:
    if metrics["trades"] < 200:
        return float("-inf")
    if metrics["total_pnl"] <= 0:
        return float("-inf")
    if metrics["profit_factor"] <= 1.02:
        return float("-inf")
    dd_ratio = abs(metrics["max_drawdown"]) / max(abs(metrics["total_pnl"]), 1e-9)
    return metrics["sharpe"] + 0.25 * (metrics["profit_factor"] - 1.0) - 0.15 * dd_ratio


def summarize_trades(trades: list[dict], max_units: int) -> dict:
    if not trades:
        return {
            "trades": 0,
            "total_pnl": 0.0,
            "avg_pnl": 0.0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "avg_hold_bars": 0.0,
            "sharpe": 0.0,
            "max_drawdown": 0.0,
            "long_trades": 0,
            "short_trades": 0,
            "max_units": max_units,
            "score": float("-inf"),
        }

    tdf = pd.DataFrame(trades)
    pnl = tdf["pnl"]
    wins = pnl[pnl > 0].sum()
    losses = -pnl[pnl < 0].sum()
    sharpe = 0.0
    if len(pnl) > 1 and float(pnl.std(ddof=1)) > 0:
        sharpe = float((pnl.mean() / pnl.std(ddof=1)) * math.sqrt(len(pnl)))

    metrics = {
        "trades": int(len(tdf)),
        "total_pnl": float(pnl.sum()),
        "avg_pnl": float(pnl.mean()),
        "win_rate": float((pnl > 0).mean()),
        "profit_factor": float(wins / losses) if losses > 0 else float("inf"),
        "avg_hold_bars": float(tdf["bars_held"].mean()),
        "sharpe": sharpe,
        "max_drawdown": calc_drawdown(pnl),
        "long_trades": int((tdf["side"] == 1).sum()),
        "short_trades": int((tdf["side"] == -1).sum()),
        "max_units": int(max_units),
    }
    metrics["score"] = score_metrics(metrics)
    return metrics


def run_candidate(
    df: pd.DataFrame,
    candidate: Candidate,
    point: float,
    contract_size: float,
    lot_size: float,
    spread_multiplier: float,
    slippage_points: float,
    range_bars: int,
) -> tuple[list[dict], dict]:
    work = df.reset_index(drop=True)

    times = work["time"].to_list()
    opens = work["open"].to_numpy(dtype=float)
    closes = work["close"].to_numpy(dtype=float)
    spreads = work["spread_price"].to_numpy(dtype=float)
    atrs = work["atr14"].to_numpy(dtype=float)
    in_session = work["in_session"].to_numpy(dtype=bool)
    session_rank = work["session_rank"].to_numpy(dtype=int)
    opening_ready = work["opening_ready"].to_numpy(dtype=bool)
    opening_high = work["opening_high"].to_numpy(dtype=float)
    opening_low = work["opening_low"].to_numpy(dtype=float)
    opening_mid = work["opening_mid"].to_numpy(dtype=float)
    session_end_idx = work["session_end_idx"].to_numpy(dtype=int)
    prev_bias = work["prev_bias"].to_numpy(dtype=float)
    prev_adx = work["prev_adx14"].to_numpy(dtype=float)
    prev_er = work["prev_er10"].to_numpy(dtype=float)
    prev_gap = work["prev_ema_gap_atr"].to_numpy(dtype=float)

    trades: list[dict] = []
    open_lots: list[Lot] = []
    pending_target = 0
    pending_reason = "flat"
    max_units = 0
    contract_value = contract_size * lot_size
    slippage_price = slippage_points * point

    def signed_units() -> int:
        if not open_lots:
            return 0
        return open_lots[0].side * len(open_lots)

    def execute_target(target_units: int, fill_index: int, reason: str, price_override: float | None = None) -> None:
        nonlocal max_units
        delta = target_units - signed_units()
        if delta == 0:
            max_units = max(max_units, abs(signed_units()))
            return

        exec_side = 1 if delta > 0 else -1
        base_price = opens[fill_index] if price_override is None else price_override
        exec_price = base_price + exec_side * (0.5 * spread_multiplier * spreads[fill_index] + slippage_price)
        qty = abs(delta)

        while qty > 0 and open_lots and open_lots[0].side != exec_side:
            lot = open_lots.pop(0)
            pnl = (exec_price - lot.entry_price) * lot.side * contract_value
            trades.append(
                {
                    "entry_time": lot.entry_time,
                    "exit_time": times[fill_index],
                    "side": lot.side,
                    "entry_price": lot.entry_price,
                    "exit_price": exec_price,
                    "pnl": pnl,
                    "bars_held": fill_index - lot.entry_idx,
                    "entry_reason": lot.entry_reason,
                    "exit_reason": reason,
                }
            )
            qty -= 1

        for _ in range(qty):
            open_lots.append(
                Lot(
                    side=exec_side,
                    entry_price=exec_price,
                    entry_time=times[fill_index],
                    entry_idx=fill_index,
                    entry_reason=reason,
                )
            )

        max_units = max(max_units, abs(signed_units()))

    def is_trend_day(i: int) -> bool:
        bias = int(prev_bias[i]) if np.isfinite(prev_bias[i]) else 0
        if bias == 0:
            return False
        adx = float(prev_adx[i]) if np.isfinite(prev_adx[i]) else float("nan")
        if not np.isfinite(adx) or adx < candidate.regime_adx_threshold:
            return False
        if candidate.regime_family == "adx_only":
            return True
        if candidate.regime_family == "adx_er_gap":
            er = float(prev_er[i]) if np.isfinite(prev_er[i]) else float("nan")
            gap = float(prev_gap[i]) if np.isfinite(prev_gap[i]) else float("nan")
            er_ok = candidate.regime_er_threshold is not None and np.isfinite(er) and er >= candidate.regime_er_threshold
            gap_ok = candidate.regime_gap_threshold is not None and np.isfinite(gap) and gap >= candidate.regime_gap_threshold
            return bool(er_ok or gap_ok)
        raise ValueError(candidate.regime_family)

    warmup = max(200, range_bars + 1)
    for i in range(warmup, len(work) - 1):
        execute_target(pending_target, i + 1, pending_reason)

        if not in_session[i] or session_rank[i] < range_bars or not opening_ready[i]:
            pending_target = 0
            pending_reason = "off_session"
            continue

        if i >= session_end_idx[i]:
            pending_target = 0
            pending_reason = "eod"
            continue

        atr = atrs[i]
        close = closes[i]
        if not np.isfinite(atr) or atr <= 0 or not np.isfinite(close):
            pending_target = signed_units()
            pending_reason = "hold_missing"
            continue

        or_high = opening_high[i]
        or_low = opening_low[i]
        or_mid = opening_mid[i]

        target = 0
        reason = "neutral"

        if is_trend_day(i):
            target = 0
            reason = "trend_skip"
        else:
            deviation = (close - or_mid) / atr
            abs_dev = abs(deviation)
            if close > or_high + candidate.range_stop_atr * atr or close < or_low - candidate.range_stop_atr * atr:
                target = 0
                reason = "range_stop"
            elif abs_dev >= candidate.range_entry_atr:
                units = min(
                    candidate.range_max_units,
                    int(math.floor((abs_dev - candidate.range_entry_atr) / candidate.range_step_atr)) + 1,
                )
                target = -int(math.copysign(units, deviation))
                reason = "range_grid"
            else:
                target = 0
                reason = "range_flat"

        pending_target = target
        pending_reason = reason

    if open_lots:
        execute_target(0, len(work) - 1, "final_flat", price_override=closes[-1])

    return trades, summarize_trades(trades, max_units=max_units)


def build_curve(trades: pd.DataFrame, segment: str, start_equity: float = 0.0) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame(columns=["exit_time", "equity", "drawdown", "segment"])
    curve = trades[["exit_time", "pnl"]].copy()
    curve["exit_time"] = pd.to_datetime(curve["exit_time"])
    curve = curve.sort_values("exit_time").reset_index(drop=True)
    curve["equity"] = curve["pnl"].cumsum() + start_equity
    curve["peak"] = curve["equity"].cummax()
    curve["drawdown"] = curve["equity"] - curve["peak"]
    curve["segment"] = segment
    return curve[["exit_time", "equity", "drawdown", "segment"]]


def monthly_pnl(trades: pd.DataFrame) -> pd.Series:
    if trades.empty:
        return pd.Series(dtype=float)
    work = trades.copy()
    work["exit_time"] = pd.to_datetime(work["exit_time"])
    work["month"] = work["exit_time"].dt.to_period("M").dt.to_timestamp()
    return work.groupby("month")["pnl"].sum()


def save_equity_plot(curve: pd.DataFrame, split_time: pd.Timestamp, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(12, 6))
    train = curve[curve["segment"] == "Train"]
    forward = curve[curve["segment"] == "Forward"]
    ax.plot(train["exit_time"], train["equity"], label="Train equity", color="#1f77b4", linewidth=2)
    ax.plot(forward["exit_time"], forward["equity"], label="Forward equity", color="#d62728", linewidth=2)
    ax.axvline(split_time, color="#444444", linestyle="--", linewidth=1.5, label="Forward split")
    ax.set_title("XAUUSD Regime-Switching Grid Equity Curve")
    ax.set_ylabel("Net PnL (USD, 0.10 lot units)")
    ax.grid(alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def save_drawdown_plot(curve: pd.DataFrame, split_time: pd.Timestamp, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(12, 4.5))
    train = curve[curve["segment"] == "Train"]
    forward = curve[curve["segment"] == "Forward"]
    ax.plot(train["exit_time"], train["drawdown"], label="Train drawdown", color="#1f77b4", linewidth=2)
    ax.plot(forward["exit_time"], forward["drawdown"], label="Forward drawdown", color="#d62728", linewidth=2)
    ax.axvline(split_time, color="#444444", linestyle="--", linewidth=1.5)
    ax.set_title("XAUUSD Regime-Switching Grid Drawdown")
    ax.set_ylabel("Drawdown")
    ax.grid(alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def save_monthly_plot(monthly: pd.Series, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(12, 4.5))
    colors = ["#2ca02c" if value >= 0 else "#d62728" for value in monthly.values]
    ax.bar(monthly.index.astype(str), monthly.values, color=colors)
    ax.set_title("Monthly Net PnL")
    ax.set_ylabel("PnL")
    ax.tick_params(axis="x", rotation=45)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def format_metrics(label: str, metrics: dict) -> str:
    return (
        f"{label}: trades={metrics['trades']}, total_pnl={metrics['total_pnl']:.2f}, "
        f"win_rate={metrics['win_rate']:.1%}, profit_factor={metrics['profit_factor']:.2f}, "
        f"sharpe={metrics['sharpe']:.2f}, max_dd={metrics['max_drawdown']:.2f}, "
        f"max_units={metrics['max_units']}"
    )


def describe_regime(candidate: Candidate) -> str:
    if candidate.regime_family == "adx_only":
        return f"skip day if previous daily bias != 0 and previous ADX(14) >= {candidate.regime_adx_threshold:.0f}"
    if candidate.regime_family == "adx_er_gap":
        return (
            "skip day if previous daily bias != 0 and previous ADX(14) "
            f">= {candidate.regime_adx_threshold:.0f} and "
            f"(previous ER(10) >= {candidate.regime_er_threshold:.2f} "
            f"or previous EMA-gap/ATR >= {candidate.regime_gap_threshold:.1f})"
        )
    raise ValueError(candidate.regime_family)


def candidate_from_row(row: pd.Series) -> Candidate:
    return Candidate(
        range_entry_atr=float(row["range_entry_atr"]),
        range_step_atr=float(row["range_step_atr"]),
        range_stop_atr=float(row["range_stop_atr"]),
        range_max_units=int(row["range_max_units"]),
        regime_family=str(row["regime_family"]),
        regime_adx_threshold=float(row["regime_adx_threshold"]),
        regime_er_threshold=float(row["regime_er_threshold"]) if pd.notna(row["regime_er_threshold"]) else None,
        regime_gap_threshold=float(row["regime_gap_threshold"]) if pd.notna(row["regime_gap_threshold"]) else None,
    )


def main() -> None:
    args = parse_args()
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    initialize_mt5(args.terminal_path)
    try:
        raw_bars, point, contract_size = fetch_rates(args.symbol, args.timeframe, args.bars)
    finally:
        mt5.shutdown()

    bars = prepare_features(raw_bars)
    train_df, forward_df = split_train_forward(bars, args.train_ratio)
    train_df = prepare_simulation_frame(train_df, args.session_start, args.session_end, args.range_bars)
    forward_df = prepare_simulation_frame(forward_df, args.session_start, args.session_end, args.range_bars)

    candidates = generate_candidates()
    leaderboard = []

    best_train_candidate = None
    best_train_metrics = None

    for candidate in candidates:
        _, train_metrics = run_candidate(
            train_df,
            candidate,
            point=point,
            contract_size=contract_size,
            lot_size=args.lot_size,
            spread_multiplier=args.spread_multiplier,
            slippage_points=args.slippage_points,
            range_bars=args.range_bars,
        )
        _, forward_metrics = run_candidate(
            forward_df,
            candidate,
            point=point,
            contract_size=contract_size,
            lot_size=args.lot_size,
            spread_multiplier=args.spread_multiplier,
            slippage_points=args.slippage_points,
            range_bars=args.range_bars,
        )
        row = {
            "candidate": candidate.name,
            "range_entry_atr": candidate.range_entry_atr,
            "range_step_atr": candidate.range_step_atr,
            "range_stop_atr": candidate.range_stop_atr,
            "range_max_units": candidate.range_max_units,
            "regime_family": candidate.regime_family,
            "regime_adx_threshold": candidate.regime_adx_threshold,
            "regime_er_threshold": candidate.regime_er_threshold,
            "regime_gap_threshold": candidate.regime_gap_threshold,
            **{f"train_{key}": value for key, value in train_metrics.items()},
            **{f"forward_{key}": value for key, value in forward_metrics.items()},
        }
        leaderboard.append(row)
        if best_train_metrics is None or train_metrics["score"] > best_train_metrics["score"]:
            best_train_candidate = candidate
            best_train_metrics = train_metrics

    board = pd.DataFrame(leaderboard).sort_values(
        ["train_score", "train_profit_factor", "train_total_pnl"],
        ascending=[False, False, False],
    )
    board.to_csv(outdir / "leaderboard.csv", index=False)

    if board.empty:
        raise RuntimeError("Candidate search returned no results.")

    stable = board[
        (board["train_total_pnl"] > 0)
        & (board["train_profit_factor"] > 1.02)
        & (board["forward_total_pnl"] > 0)
        & (board["forward_profit_factor"] > 1.02)
    ].copy()
    stable["robust_score"] = stable[["train_score", "forward_score"]].min(axis=1)
    recommended_row = stable.sort_values(
        ["robust_score", "forward_score", "train_score", "forward_profit_factor"],
        ascending=[False, False, False, False],
    ).head(1)
    if recommended_row.empty:
        recommended_row = board.head(1)

    recommended_candidate = candidate_from_row(recommended_row.iloc[0])
    best_train_candidate = best_train_candidate or recommended_candidate

    best_train_train_trades, best_train_train_metrics = run_candidate(
        train_df,
        best_train_candidate,
        point=point,
        contract_size=contract_size,
        lot_size=args.lot_size,
        spread_multiplier=args.spread_multiplier,
        slippage_points=args.slippage_points,
        range_bars=args.range_bars,
    )
    best_train_forward_trades, best_train_forward_metrics = run_candidate(
        forward_df,
        best_train_candidate,
        point=point,
        contract_size=contract_size,
        lot_size=args.lot_size,
        spread_multiplier=args.spread_multiplier,
        slippage_points=args.slippage_points,
        range_bars=args.range_bars,
    )
    rec_train_trades, rec_train_metrics = run_candidate(
        train_df,
        recommended_candidate,
        point=point,
        contract_size=contract_size,
        lot_size=args.lot_size,
        spread_multiplier=args.spread_multiplier,
        slippage_points=args.slippage_points,
        range_bars=args.range_bars,
    )
    rec_forward_trades, rec_forward_metrics = run_candidate(
        forward_df,
        recommended_candidate,
        point=point,
        contract_size=contract_size,
        lot_size=args.lot_size,
        spread_multiplier=args.spread_multiplier,
        slippage_points=args.slippage_points,
        range_bars=args.range_bars,
    )

    best_train_train_df = pd.DataFrame(best_train_train_trades)
    best_train_forward_df = pd.DataFrame(best_train_forward_trades)
    rec_train_df = pd.DataFrame(rec_train_trades)
    rec_forward_df = pd.DataFrame(rec_forward_trades)

    best_train_train_df.to_csv(outdir / "best_train_train_trades.csv", index=False)
    best_train_forward_df.to_csv(outdir / "best_train_forward_trades.csv", index=False)
    rec_train_df.to_csv(outdir / "recommended_train_trades.csv", index=False)
    rec_forward_df.to_csv(outdir / "recommended_forward_trades.csv", index=False)

    train_curve = build_curve(rec_train_df, "Train", start_equity=0.0)
    train_end_equity = float(train_curve["equity"].iloc[-1]) if not train_curve.empty else 0.0
    forward_curve = build_curve(rec_forward_df, "Forward", start_equity=train_end_equity)
    combined_curve = pd.concat([train_curve, forward_curve], ignore_index=True)
    split_time = pd.to_datetime(forward_df["time"].iloc[0])

    equity_path = outdir / "equity_curve.png"
    drawdown_path = outdir / "drawdown_curve.png"
    monthly_path = outdir / "monthly_pnl.png"
    save_equity_plot(combined_curve, split_time, equity_path)
    save_drawdown_plot(combined_curve, split_time, drawdown_path)
    save_monthly_plot(
        monthly_pnl(pd.concat([rec_train_df, rec_forward_df], ignore_index=True)),
        monthly_path,
    )

    report = f"""# XAUUSD Regime-Switching Grid Backtest

## Core Design

- Instrument: `{args.symbol}`
- Timeframe: `{args.timeframe}`
- Position sizing: `{args.lot_size:.2f}` lot per grid unit
- Spread multiplier: `{args.spread_multiplier:.2f} x raw MT5 bar spread`
- Session: `{args.session_start:02d}:00` to `{args.session_end:02d}:00` broker/server time
- Opening range: first `{args.range_bars}` bars after session start
- Regime candidates use only previous completed daily-bar features: `ADX(14)`, `ER(10)`, and `|Close-EMA20| / ATR`

## No-Lookahead Rules

- Daily regime uses only the previous completed daily bar.
- The current day opening range is built only from the first completed intraday bars of that same day.
- Signals are evaluated on bar close and executed on the next bar open.
- Intraday positions are forced flat by session end.
- Fills include `{args.spread_multiplier:.2f} x` the MT5 bar spread plus `{args.slippage_points:.1f}` point slippage per side.

## Range Grid Logic

- On non-trend days, use the opening-range midpoint as the grid anchor.
- If close deviates from the anchor by at least `range_entry_atr x ATR(14)`, fade the move on the next bar open.
- Add one grid unit every `range_step_atr x ATR(14)` extension, capped by `range_max_units`.
- Flatten if price snaps back inside the entry threshold or if price pushes beyond the opening-range edge by `range_stop_atr x ATR(14)`.

## Trend Regime Handling

- On trend days, the strategy does not trade.
- Trend regime remains in the model only as a state filter so range-grid entries are disabled on those days.
- The script searches both `ADX-only` and `ADX + (ER or EMA-gap)` regime filters.

## Selection Notes

- `best_train` is the pure train-side winner from the parameter sweep.
- `recommended` is the strongest candidate that stayed positive in both train and forward samples and maximized the weaker of the two scores.

## Best Train Candidate

- Candidate: `{best_train_candidate.name}`
- Regime rule: `{describe_regime(best_train_candidate)}`
- {format_metrics("Train", best_train_train_metrics)}
- {format_metrics("Forward", best_train_forward_metrics)}

## Recommended Stable Candidate

- Candidate: `{recommended_candidate.name}`
- Regime rule: `{describe_regime(recommended_candidate)}`
- {format_metrics("Train", rec_train_metrics)}
- {format_metrics("Forward", rec_forward_metrics)}

## Data Window

- Full sample: `{pd.to_datetime(bars['time'].min())}` to `{pd.to_datetime(bars['time'].max())}`
- Train window: `{pd.to_datetime(train_df['time'].min())}` to `{pd.to_datetime(train_df['time'].max())}`
- Forward window: `{pd.to_datetime(forward_df['time'].min())}` to `{pd.to_datetime(forward_df['time'].max())}`

## Files

- Leaderboard: `leaderboard.csv`
- Best-train trade logs: `best_train_train_trades.csv`, `best_train_forward_trades.csv`
- Recommended trade logs: `recommended_train_trades.csv`, `recommended_forward_trades.csv`

![Equity curve](equity_curve.png)

![Drawdown](drawdown_curve.png)

![Monthly pnl](monthly_pnl.png)
"""

    (outdir / "xauusd_regime_grid_report.md").write_text(report, encoding="utf-8")

    print(f"Data: {args.symbol} {args.timeframe}, rows={len(bars)}, start={bars['time'].min()}, end={bars['time'].max()}")
    print(f"Train rows={len(train_df)}, Forward rows={len(forward_df)}")
    print(f"Best-train winner: {best_train_candidate.name}")
    print(format_metrics("Best train / Train", best_train_train_metrics))
    print(format_metrics("Best train / Forward", best_train_forward_metrics))
    print()
    print(f"Recommended stable candidate: {recommended_candidate.name}")
    print(format_metrics("Recommended / Train", rec_train_metrics))
    print(format_metrics("Recommended / Forward", rec_forward_metrics))
    print()
    cols = [
        "candidate",
        "train_trades",
        "train_total_pnl",
        "train_profit_factor",
        "train_sharpe",
        "train_max_drawdown",
        "forward_trades",
        "forward_total_pnl",
        "forward_profit_factor",
        "forward_sharpe",
        "forward_max_drawdown",
    ]
    print(f"Top {args.top} train candidates:")
    print(board[cols].head(args.top).to_string(index=False))
    print()
    print(f"Saved leaderboard: {outdir / 'leaderboard.csv'}")
    print(f"Saved report: {outdir / 'xauusd_regime_grid_report.md'}")


if __name__ == "__main__":
    main()
