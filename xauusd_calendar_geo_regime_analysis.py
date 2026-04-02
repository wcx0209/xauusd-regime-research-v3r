from __future__ import annotations

import argparse
import math
import re
import time
from html import unescape
from pathlib import Path
from typing import Callable

import MetaTrader5 as mt5
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests

from xauusd_regime_switching_grid_backtest import fetch_rates, initialize_mt5


ROOT = Path(__file__).resolve().parent
DEFAULT_CALENDAR_PATH = ROOT / "data" / "codex_native_calendar_majors.csv"
WIKI_API_URL = "https://en.wikipedia.org/w/api.php"
WIKI_HEADERS = {
    "User-Agent": "CodexResearchBot/1.0 (research workflow for local XAUUSD study; contact unavailable)"
}
WIKI_MONTHS = [
    (2025, 10),
    (2025, 11),
    (2025, 12),
    (2026, 1),
    (2026, 2),
    (2026, 3),
]


MACRO_CATEGORY_RULES: list[tuple[str, Callable[[str, str, str], bool]]] = [
    (
        "FED_POLICY",
        lambda currency, code, name: currency == "USD"
        and any(
            token in code or token in name
            for token in [
                "fed-interest-rate-decision",
                "fomc-press-conference",
                "fed-chair-powell-speech",
                "fomc",
            ]
        ),
    ),
    (
        "US_INFLATION",
        lambda currency, code, name: currency == "USD"
        and any(
            token in code or token in name
            for token in [
                "consumer-price-index",
                "producer-price-index",
                "pce-price-index",
                "core-pce-price-index",
                "inflation",
            ]
        ),
    ),
    (
        "US_LABOR_MAJOR",
        lambda currency, code, name: currency == "USD"
        and any(
            token in code or token in name
            for token in [
                "nonfarm-payrolls",
                "unemployment-rate",
                "average-hourly-earnings",
            ]
        ),
    ),
    (
        "US_LABOR_SECONDARY",
        lambda currency, code, name: currency == "USD"
        and any(
            token in code or token in name
            for token in [
                "initial-jobless-claims",
                "adp-nonfarm-employment-change",
                "jolts-job-openings",
            ]
        ),
    ),
    (
        "US_GROWTH_ACTIVITY",
        lambda currency, code, name: currency == "USD"
        and any(
            token in code or token in name
            for token in [
                "gross-domestic-product",
                "retail-sales",
                "consumer-confidence",
                "ism-",
                "markit-",
                "chicago-pmi",
                "philadelphia-fed",
                "durable-goods",
            ]
        ),
    ),
    (
        "US_TREASURY_OIL",
        lambda currency, code, name: currency == "USD"
        and any(
            token in code or token in name
            for token in [
                "10-year-note-auction",
                "30-year-bond-auction",
                "eia-crude-oil-stocks-change",
            ]
        ),
    ),
    (
        "ECB_POLICY",
        lambda currency, code, name: currency == "EUR"
        and any(
            token in code or token in name
            for token in [
                "ecb-deposit-rate-decision",
                "ecb-interest-rate-decision",
                "ecb-monetary-policy-press-conference",
                "ecb-president-lagarde-speech",
            ]
        ),
    ),
    (
        "BOJ_POLICY",
        lambda currency, code, name: currency == "JPY"
        and any(
            token in code or token in name
            for token in [
                "boj-interest-rate-decision",
                "boj-press-conference",
            ]
        ),
    ),
]


GEO_THEME_RULES = {
    "GEO_MIDDLE_EAST": {
        "regions": [
            "israel",
            "gaza",
            "hamas",
            "hezbollah",
            "iran",
            "syria",
            "syrian",
            "lebanon",
            "houthi",
            "red sea",
            "yemen",
            "hormuz",
        ],
        "actions": [
            "airstrike*",
            "strike*",
            "missile*",
            "drone*",
            "attack*",
            "retaliat*",
            "ceasefire",
            "killed",
            "sanction*",
            "nuclear",
            "hostage",
            "tanker*",
            "shipping",
        ],
    },
    "GEO_RUSSIA_UKRAINE": {
        "regions": [
            "russia",
            "ukraine",
            "moscow",
            "kyiv",
            "crimea",
            "black sea",
            "chernobyl",
            "donetsk",
            "kherson",
        ],
        "actions": [
            "strike*",
            "missile*",
            "drone*",
            "attack*",
            "ceasefire",
            "sanction*",
            "pipeline",
            "energy",
            "offensive*",
            "killed",
        ],
    },
    "GEO_US_CHINA_TAIWAN_TRADE": {
        "regions": [
            "china",
            "beijing",
            "taiwan",
            "south china sea",
            "rare earth",
            "semiconductor*",
            "export control*",
        ],
        "actions": [
            "tariff*",
            "sanction*",
            "drill*",
            "military",
            "naval",
            "trade war",
            "export control*",
            "retaliat*",
            "blockade",
        ],
    },
    "GEO_KOREA_PENINSULA": {
        "regions": [
            "north korea",
            "south korea",
            "pyongyang",
            "korean peninsula",
        ],
        "actions": [
            "missile*",
            "nuclear",
            "launch*",
            "test*",
            "drill*",
            "military",
            "sanction*",
        ],
    },
    "GEO_INDIA_PAKISTAN": {
        "regions": [
            "india",
            "pakistan",
            "kashmir",
        ],
        "actions": [
            "strike*",
            "attack*",
            "ceasefire",
            "military",
            "shelling",
            "missile*",
            "border",
        ],
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Measure which macro and geopolitical event families shift XAUUSD intraday volatility regime."
    )
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--timeframe", default="M15")
    parser.add_argument("--bars", type=int, default=30000)
    parser.add_argument(
        "--terminal-path",
        default=r"C:\MT5PortableCodex\terminal64.exe",
    )
    parser.add_argument(
        "--calendar-path",
        default=str(DEFAULT_CALENDAR_PATH),
    )
    parser.add_argument("--outdir", default="artifacts_xauusd_calendar_geo_regime")
    return parser.parse_args()


def load_native_calendar(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path, sep="\t", encoding="gb18030")
    frame["time"] = pd.to_datetime(frame["time"], format="%Y.%m.%d %H:%M:%S")
    frame["currency_filter"] = frame["currency_filter"].astype(str).str.upper()
    frame["importance_name"] = frame["importance_name"].astype(str).str.lower()
    frame["event_code"] = frame["event_code"].fillna("").astype(str).str.lower()
    frame["event_name"] = frame["event_name"].fillna("").astype(str).str.lower()
    frame = frame.sort_values(["time", "currency_filter", "event_code"]).reset_index(drop=True)
    return frame


def assign_macro_category(currency: str, event_code: str, event_name: str) -> str | None:
    for category, rule in MACRO_CATEGORY_RULES:
        if rule(currency, event_code, event_name):
            return category
    if currency == "USD":
        return "USD_HIGH_OTHER"
    return None


def build_macro_daily_flags(events: pd.DataFrame, start_date: pd.Timestamp, end_date: pd.Timestamp, outdir: Path) -> pd.DataFrame:
    scoped = events.loc[
        (events["time"] >= start_date)
        & (events["time"] <= end_date + pd.Timedelta(days=1))
        & (events["importance_name"] == "high")
    ].copy()
    scoped["event_date"] = scoped["time"].dt.floor("D")
    scoped["macro_family"] = scoped.apply(
        lambda row: assign_macro_category(str(row["currency_filter"]), str(row["event_code"]), str(row["event_name"])),
        axis=1,
    )
    scoped = scoped.loc[scoped["macro_family"].notna()].copy()
    if scoped.empty:
        return pd.DataFrame({"date": pd.date_range(start_date, end_date, freq="D")})

    scoped["macro_family"] = scoped["macro_family"].astype(str)
    by_day = (
        scoped.groupby(["event_date", "macro_family"], as_index=False)
        .agg(
            event_rows=("event_code", "count"),
            event_codes=("event_code", lambda s: " | ".join(sorted(set(s))[:4])),
            event_names=("event_name", lambda s: " | ".join(sorted(set(s))[:4])),
        )
        .rename(columns={"event_date": "date"})
    )
    by_day.to_csv(outdir / "macro_event_days_long.csv", index=False)

    daily = pd.DataFrame({"date": pd.date_range(start_date, end_date, freq="D")})
    daily["USD_HIGH_ANY"] = False
    usd_any_days = scoped.loc[scoped["currency_filter"] == "USD", "event_date"].drop_duplicates()
    if not usd_any_days.empty:
        daily.loc[daily["date"].isin(usd_any_days), "USD_HIGH_ANY"] = True

    for family in sorted(scoped["macro_family"].unique()):
        family_days = scoped.loc[scoped["macro_family"] == family, "event_date"].drop_duplicates()
        daily[family] = daily["date"].isin(family_days)
    return daily


def fetch_month_html(year: int, month: int, cache_dir: Path) -> str:
    cache_path = cache_dir / f"wiki_current_events_{year}_{month:02d}.html"
    if cache_path.exists():
        return cache_path.read_text(encoding="utf-8")

    month_name = pd.Timestamp(year=year, month=month, day=1).strftime("%B")
    params = {
        "action": "parse",
        "page": f"Portal:Current events/{month_name} {year}",
        "prop": "text",
        "format": "json",
    }
    response = requests.get(WIKI_API_URL, params=params, headers=WIKI_HEADERS, timeout=60)
    response.raise_for_status()
    payload = response.json()
    html = payload["parse"]["text"]["*"]
    cache_path.write_text(html, encoding="utf-8")
    time.sleep(1.0)
    return html


def html_to_text(html: str) -> str:
    text = re.sub(r"</(li|p|div|h\d|ul|ol|table|tr)>", "\n", html, flags=re.I)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<.*?>", " ", text, flags=re.S)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_wiki_daily_texts(start_date: pd.Timestamp, end_date: pd.Timestamp, cache_dir: Path) -> pd.DataFrame:
    rows: list[dict] = []
    marker = re.compile(r'<span class="bday dtstart published updated itvstart">(\d{4}-\d{2}-\d{2})</span>')
    for year, month in WIKI_MONTHS:
        html = fetch_month_html(year, month, cache_dir)
        matches = list(marker.finditer(html))
        for idx, match in enumerate(matches):
            day = pd.Timestamp(match.group(1))
            if day < start_date or day > end_date:
                continue
            end_pos = matches[idx + 1].start() if idx + 1 < len(matches) else len(html)
            chunk = html[match.start() : end_pos]
            rows.append(
                {
                    "date": day,
                    "wiki_text": html_to_text(chunk),
                }
            )
    if not rows:
        raise RuntimeError("No Wikipedia current-events pages were parsed for the requested date range.")
    daily = pd.DataFrame(rows).drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
    return daily


def keyword_hits(text: str, keywords: list[str]) -> int:
    hits = 0
    for keyword in keywords:
        if keyword.endswith("*"):
            root = re.escape(keyword[:-1])
            pattern = rf"(?<![a-z]){root}[a-z]*(?![a-z])"
        else:
            pattern = rf"(?<![a-z]){re.escape(keyword)}(?![a-z])"
        hits += len(re.findall(pattern, text))
    return hits


def map_to_next_trading_date(event_date: pd.Timestamp, trading_dates: pd.Index) -> pd.Timestamp | pd.NaT:
    pos = trading_dates.searchsorted(event_date)
    if pos >= len(trading_dates):
        return pd.NaT
    return pd.Timestamp(trading_dates[pos])


def align_geo_dates_to_trading_days(wiki_daily: pd.DataFrame, trading_dates: pd.Index) -> pd.DataFrame:
    aligned = wiki_daily.copy()
    aligned["effective_date"] = aligned["date"].apply(lambda value: map_to_next_trading_date(pd.Timestamp(value), trading_dates))
    aligned = aligned.loc[aligned["effective_date"].notna()].copy()
    grouped = (
        aligned.groupby("effective_date", as_index=False)
        .agg(
            source_dates=("date", lambda s: ",".join(pd.Series(sorted(set(pd.to_datetime(s).dt.strftime("%Y-%m-%d")))).tolist())),
            wiki_text=("wiki_text", lambda s: " ".join(map(str, s))),
        )
        .rename(columns={"effective_date": "date"})
        .sort_values("date")
        .reset_index(drop=True)
    )
    return grouped


def build_geo_daily_flags(wiki_daily: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    out = wiki_daily.copy()
    out["text_lower"] = out["wiki_text"].str.lower()
    example_rows: list[dict] = []

    for theme, rules in GEO_THEME_RULES.items():
        region_col = f"{theme}_region_hits"
        action_col = f"{theme}_action_hits"
        score_col = f"{theme}_score"
        flag_col = f"{theme}_SHOCK"

        out[region_col] = out["text_lower"].apply(lambda text: keyword_hits(text, rules["regions"]))
        out[action_col] = out["text_lower"].apply(lambda text: keyword_hits(text, rules["actions"]))
        out[score_col] = out[region_col] + 1.5 * out[action_col]

        positive_scores = out.loc[out[score_col] > 0, score_col]
        if positive_scores.empty:
            threshold = math.inf
        else:
            quantile_threshold = float(positive_scores.quantile(0.85))
            threshold = max(3.0, quantile_threshold)
        out[flag_col] = out[score_col] >= threshold

        theme_examples = (
            out.loc[out[flag_col], ["date", "source_dates", "wiki_text", score_col, region_col, action_col]]
            .sort_values(score_col, ascending=False)
            .head(5)
        )
        for _, row in theme_examples.iterrows():
            example_rows.append(
                {
                    "theme": theme,
                    "date": row["date"],
                    "source_dates": row.get("source_dates", ""),
                    "score": float(row[score_col]),
                    "region_hits": int(row[region_col]),
                    "action_hits": int(row[action_col]),
                    "snippet": str(row["wiki_text"])[:260],
                }
            )

    shock_cols = [f"{theme}_SHOCK" for theme in GEO_THEME_RULES]
    out["GEO_ANY_SHOCK"] = out[shock_cols].any(axis=1)

    examples = pd.DataFrame(example_rows).sort_values(["theme", "score"], ascending=[True, False]).reset_index(drop=True)
    out = out.drop(columns=["text_lower"])
    return out, examples


def build_daily_regime(raw_bars: pd.DataFrame) -> pd.DataFrame:
    bars = raw_bars.copy()
    bars["date"] = bars["time"].dt.floor("D")
    daily = (
        bars.groupby("date", as_index=False)
        .agg(
            day_open=("open", "first"),
            day_high=("high", "max"),
            day_low=("low", "min"),
            day_close=("close", "last"),
            bar_count=("time", "size"),
        )
        .sort_values("date")
        .reset_index(drop=True)
    )
    daily["day_range"] = daily["day_high"] - daily["day_low"]
    prior_close = daily["day_close"].shift(1)
    daily["true_range"] = pd.concat(
        [
            daily["day_high"] - daily["day_low"],
            (daily["day_high"] - prior_close).abs(),
            (daily["day_low"] - prior_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    daily["prior20_range_median"] = daily["day_range"].shift(1).rolling(20, min_periods=10).median()
    daily["prior20_tr_median"] = daily["true_range"].shift(1).rolling(20, min_periods=10).median()
    daily["range_ratio"] = daily["day_range"] / daily["prior20_range_median"]
    daily["true_range_ratio"] = daily["true_range"] / daily["prior20_tr_median"]
    daily["body_ratio"] = (daily["day_close"] - daily["day_open"]).abs() / daily["day_range"].replace(0, np.nan)
    daily["abs_return_pct"] = (daily["day_close"] - daily["day_open"]).abs() / daily["day_open"].replace(0, np.nan) * 100.0
    daily["high_vol_day"] = daily["range_ratio"] >= 1.25
    daily["trend_day"] = (daily["range_ratio"] >= 1.25) & (daily["body_ratio"] >= 0.55)
    daily["regime_score"] = daily["range_ratio"] * (0.5 + 0.5 * daily["body_ratio"].fillna(0.0))
    return daily


def summarize_event_impact(
    frame: pd.DataFrame,
    label: str,
    flag_col: str,
    baseline_mask: pd.Series | None = None,
) -> dict | None:
    if flag_col not in frame.columns:
        return None
    event_days = frame.loc[frame[flag_col]].copy()
    if event_days.empty:
        return None

    if baseline_mask is None:
        baseline = frame.loc[~frame[flag_col]].copy()
    else:
        baseline = frame.loc[baseline_mask].copy()
    baseline = baseline.loc[baseline["range_ratio"].notna()]
    event_days = event_days.loc[event_days["range_ratio"].notna()]
    if event_days.empty or baseline.empty:
        return None

    avg_range = float(event_days["range_ratio"].mean())
    base_range = float(baseline["range_ratio"].mean())
    avg_regime = float(event_days["regime_score"].mean())
    base_regime = float(baseline["regime_score"].mean())
    return {
        "label": label,
        "event_days": int(len(event_days)),
        "avg_range_ratio": avg_range,
        "median_range_ratio": float(event_days["range_ratio"].median()),
        "baseline_range_ratio": base_range,
        "range_lift_pct": (avg_range / base_range - 1.0) * 100.0 if base_range else np.nan,
        "avg_regime_score": avg_regime,
        "median_regime_score": float(event_days["regime_score"].median()),
        "baseline_regime_score": base_regime,
        "regime_lift_pct": (avg_regime / base_regime - 1.0) * 100.0 if base_regime else np.nan,
        "high_vol_rate": float(event_days["high_vol_day"].mean()),
        "baseline_high_vol_rate": float(baseline["high_vol_day"].mean()),
        "trend_day_rate": float(event_days["trend_day"].mean()),
        "baseline_trend_day_rate": float(baseline["trend_day"].mean()),
        "avg_abs_return_pct": float(event_days["abs_return_pct"].mean()),
        "median_abs_return_pct": float(event_days["abs_return_pct"].median()),
        "baseline_abs_return_pct": float(baseline["abs_return_pct"].mean()),
    }


def plot_event_lift(frame: pd.DataFrame, title: str, outpath: Path) -> None:
    if frame.empty:
        return
    plot_df = frame.sort_values("range_lift_pct", ascending=True).tail(10).copy()
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.barh(plot_df["label"], plot_df["range_lift_pct"], color="#b07d2b")
    ax.set_title(title)
    ax.set_xlabel("Range Lift vs Baseline (%)")
    ax.grid(axis="x", alpha=0.25)
    fig.tight_layout()
    fig.savefig(outpath, dpi=160)
    plt.close(fig)


def main() -> None:
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    cache_dir = outdir / "wiki_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    initialize_mt5(args.terminal_path)
    try:
        raw_bars, point, contract_size = fetch_rates(args.symbol, args.timeframe, args.bars)
    finally:
        mt5.shutdown()

    daily_regime = build_daily_regime(raw_bars)
    overlap_start = max(daily_regime["date"].min(), pd.Timestamp("2025-10-01"))
    overlap_end = min(daily_regime["date"].max(), pd.Timestamp("2026-03-31"))
    daily_regime = daily_regime.loc[(daily_regime["date"] >= overlap_start) & (daily_regime["date"] <= overlap_end)].copy()

    native_calendar = load_native_calendar(args.calendar_path)
    macro_daily = build_macro_daily_flags(native_calendar, overlap_start, overlap_end, outdir)

    wiki_daily_raw = extract_wiki_daily_texts(overlap_start, overlap_end, cache_dir)
    wiki_daily = align_geo_dates_to_trading_days(wiki_daily_raw, pd.Index(daily_regime["date"].drop_duplicates().sort_values()))
    geo_daily, geo_examples = build_geo_daily_flags(wiki_daily)

    merged = daily_regime.merge(macro_daily, on="date", how="left").merge(geo_daily, on="date", how="left")
    merged = merged.sort_values("date").reset_index(drop=True)

    bool_cols = [col for col in merged.columns if col.endswith("_SHOCK") or col.endswith("_ANY") or col.startswith("US_") or col in sorted(set(macro_daily.columns) - {"date"})]
    for col in bool_cols:
        if col in merged.columns:
            merged[col] = merged[col].fillna(False).astype(bool)

    macro_rows = []
    for col in sorted(c for c in macro_daily.columns if c != "date"):
        row = summarize_event_impact(merged, col, col)
        if row is not None:
            macro_rows.append(row)
    macro_rank = pd.DataFrame(macro_rows).sort_values("range_lift_pct", ascending=False).reset_index(drop=True)

    geo_rows = []
    for theme in GEO_THEME_RULES:
        flag_col = f"{theme}_SHOCK"
        row = summarize_event_impact(merged, theme, flag_col)
        if row is not None:
            row["sample_type"] = "all_theme_days"
            geo_rows.append(row)

        pure_days = merged.loc[merged[flag_col] & (~merged["USD_HIGH_ANY"]) & merged["range_ratio"].notna()].copy()
        pure_baseline = merged.loc[(~merged[flag_col]) & (~merged["USD_HIGH_ANY"]) & merged["range_ratio"].notna()].copy()
        if not pure_days.empty and not pure_baseline.empty:
            base_range = float(pure_baseline["range_ratio"].mean())
            base_regime = float(pure_baseline["regime_score"].mean())
            geo_rows.append(
                {
                    "label": f"{theme}_PURE",
                    "event_days": int(len(pure_days)),
                    "avg_range_ratio": float(pure_days["range_ratio"].mean()),
                    "median_range_ratio": float(pure_days["range_ratio"].median()),
                    "baseline_range_ratio": base_range,
                    "range_lift_pct": (float(pure_days["range_ratio"].mean()) / base_range - 1.0) * 100.0 if base_range else np.nan,
                    "avg_regime_score": float(pure_days["regime_score"].mean()),
                    "median_regime_score": float(pure_days["regime_score"].median()),
                    "baseline_regime_score": base_regime,
                    "regime_lift_pct": (float(pure_days["regime_score"].mean()) / base_regime - 1.0) * 100.0 if base_regime else np.nan,
                    "high_vol_rate": float(pure_days["high_vol_day"].mean()),
                    "baseline_high_vol_rate": float(pure_baseline["high_vol_day"].mean()),
                    "trend_day_rate": float(pure_days["trend_day"].mean()),
                    "baseline_trend_day_rate": float(pure_baseline["trend_day"].mean()),
                    "avg_abs_return_pct": float(pure_days["abs_return_pct"].mean()),
                    "median_abs_return_pct": float(pure_days["abs_return_pct"].median()),
                    "baseline_abs_return_pct": float(pure_baseline["abs_return_pct"].mean()),
                    "sample_type": "geo_without_usd_high",
                }
            )

        other_geo_cols = [f"{other_theme}_SHOCK" for other_theme in GEO_THEME_RULES if other_theme != theme]
        if other_geo_cols:
            exclusive_days = merged.loc[
                merged[flag_col]
                & (~merged["USD_HIGH_ANY"])
                & (~merged[other_geo_cols].any(axis=1))
                & merged["range_ratio"].notna()
            ].copy()
            exclusive_baseline = merged.loc[
                (~merged[flag_col]) & (~merged["USD_HIGH_ANY"]) & merged["range_ratio"].notna()
            ].copy()
            if not exclusive_days.empty and not exclusive_baseline.empty:
                base_range = float(exclusive_baseline["range_ratio"].mean())
                base_regime = float(exclusive_baseline["regime_score"].mean())
                geo_rows.append(
                    {
                        "label": f"{theme}_EXCLUSIVE",
                        "event_days": int(len(exclusive_days)),
                        "avg_range_ratio": float(exclusive_days["range_ratio"].mean()),
                        "median_range_ratio": float(exclusive_days["range_ratio"].median()),
                        "baseline_range_ratio": base_range,
                        "range_lift_pct": (float(exclusive_days["range_ratio"].mean()) / base_range - 1.0) * 100.0 if base_range else np.nan,
                        "avg_regime_score": float(exclusive_days["regime_score"].mean()),
                        "median_regime_score": float(exclusive_days["regime_score"].median()),
                        "baseline_regime_score": base_regime,
                        "regime_lift_pct": (float(exclusive_days["regime_score"].mean()) / base_regime - 1.0) * 100.0 if base_regime else np.nan,
                        "high_vol_rate": float(exclusive_days["high_vol_day"].mean()),
                        "baseline_high_vol_rate": float(exclusive_baseline["high_vol_day"].mean()),
                        "trend_day_rate": float(exclusive_days["trend_day"].mean()),
                        "baseline_trend_day_rate": float(exclusive_baseline["trend_day"].mean()),
                        "avg_abs_return_pct": float(exclusive_days["abs_return_pct"].mean()),
                        "median_abs_return_pct": float(exclusive_days["abs_return_pct"].median()),
                        "baseline_abs_return_pct": float(exclusive_baseline["abs_return_pct"].mean()),
                        "sample_type": "geo_without_usd_high_exclusive",
                    }
                )

    geo_any = summarize_event_impact(merged, "GEO_ANY_SHOCK", "GEO_ANY_SHOCK")
    if geo_any is not None:
        geo_any["sample_type"] = "all_theme_days"
        geo_rows.append(geo_any)
    geo_rank = pd.DataFrame(geo_rows).sort_values(["sample_type", "range_lift_pct"], ascending=[True, False]).reset_index(drop=True)

    combined = pd.concat(
        [
            macro_rank.assign(source="macro"),
            geo_rank.assign(source="geopolitical"),
        ],
        ignore_index=True,
    ).sort_values("range_lift_pct", ascending=False).reset_index(drop=True)

    merged.to_csv(outdir / "xau_daily_regime_with_events.csv", index=False)
    macro_rank.to_csv(outdir / "macro_event_impact_rank.csv", index=False)
    geo_rank.to_csv(outdir / "geo_event_impact_rank.csv", index=False)
    combined.to_csv(outdir / "combined_event_impact_rank.csv", index=False)
    geo_examples.to_csv(outdir / "geo_theme_examples.csv", index=False)
    wiki_daily_raw.to_csv(outdir / "wiki_current_events_daily_text_raw.csv", index=False)
    wiki_daily.to_csv(outdir / "wiki_current_events_daily_text.csv", index=False)

    plot_event_lift(macro_rank, "XAUUSD: Macro Event Range Lift", outdir / "macro_event_range_lift.png")
    plot_event_lift(
        geo_rank.loc[geo_rank["sample_type"] == "geo_without_usd_high"].copy(),
        "XAUUSD: Geopolitical Shock Range Lift (No Same-Day USD High-Impact Data)",
        outdir / "geo_event_range_lift_pure.png",
    )

    baseline = merged.loc[merged["range_ratio"].notna()].copy()
    baseline_range = float(baseline["range_ratio"].mean())
    baseline_high_vol = float(baseline["high_vol_day"].mean())
    baseline_trend = float(baseline["trend_day"].mean())

    top_macro = macro_rank.head(5)
    top_geo = geo_rank.loc[geo_rank["sample_type"] == "geo_without_usd_high"].head(5)

    lines = [
        "# XAUUSD Calendar + Geopolitical Regime Analysis",
        "",
        f"Sample: `{overlap_start.date()}` to `{overlap_end.date()}` using local `XAUUSD {args.timeframe}` MT5 bars and the MQL5 native calendar.",
        "",
        "## Baseline",
        "",
        f"- Mean daily range ratio vs prior-20-day median: `{baseline_range:.2f}`",
        f"- High-volatility day rate (`range_ratio >= 1.25`): `{baseline_high_vol:.1%}`",
        f"- Trend-day rate (`range_ratio >= 1.25` and `body_ratio >= 0.55`): `{baseline_trend:.1%}`",
        "",
        "## Top Macro Families",
        "",
    ]
    for _, row in top_macro.iterrows():
        lines.append(
            f"- `{row['label']}`: `{int(row['event_days'])}` days, mean range ratio `{row['avg_range_ratio']:.2f}`, "
            f"range lift `{row['range_lift_pct']:.1f}%`, high-vol rate `{row['high_vol_rate']:.1%}`, trend-day rate `{row['trend_day_rate']:.1%}`"
        )
    lines.extend(
        [
            "",
            "## Top Geopolitical Shock Families",
            "",
        ]
    )
    for _, row in top_geo.iterrows():
        lines.append(
            f"- `{row['label']}`: `{int(row['event_days'])}` pure geo days, mean range ratio `{row['avg_range_ratio']:.2f}`, "
            f"range lift `{row['range_lift_pct']:.1f}%`, high-vol rate `{row['high_vol_rate']:.1%}`, trend-day rate `{row['trend_day_rate']:.1%}`"
        )
    if not geo_examples.empty:
        lines.extend(["", "## Example Geopolitical Shock Dates", ""])
        for theme in sorted(geo_examples["theme"].unique()):
            subset = geo_examples.loc[geo_examples["theme"] == theme].head(3)
            for _, row in subset.iterrows():
                lines.append(
                    f"- `{theme}` trading day `{pd.Timestamp(row['date']).date()}` (source dates `{row.get('source_dates', '')}`) score `{row['score']:.1f}`: {row['snippet']}"
                )
    lines.extend(
        [
            "",
            "## Files",
            "",
            "- `xau_daily_regime_with_events.csv`",
            "- `macro_event_impact_rank.csv`",
            "- `geo_event_impact_rank.csv`",
            "- `combined_event_impact_rank.csv`",
            "- `geo_theme_examples.csv`",
            "- `macro_event_range_lift.png`",
            "- `geo_event_range_lift_pure.png`",
        ]
    )
    (outdir / "summary.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"Saved report: {outdir / 'summary.md'}")
    print(f"Saved combined ranking: {outdir / 'combined_event_impact_rank.csv'}")
    print(f"Point={point} ContractSize={contract_size}")


if __name__ == "__main__":
    args = parse_args()
    main()
