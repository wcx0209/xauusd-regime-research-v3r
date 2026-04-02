from __future__ import annotations

import argparse
import json
import re
import ssl
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import MetaTrader5 as mt5
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression, Ridge

from xauusd_calendar_geo_regime_analysis import (
    align_geo_dates_to_trading_days,
    build_daily_regime,
    build_geo_daily_flags,
    build_macro_daily_flags,
    load_native_calendar,
)
from xauusd_regime_factor_research import (
    build_cross_asset_features,
    build_price_structure_features,
    build_session_features,
)
from xauusd_regime_factor_research_v2 import (
    add_geo_intensity,
    add_intensity_features,
    add_london_us_break_flags,
    build_open_window_features,
)
from xauusd_regime_factor_research_v3 import build_proxy_features
from xauusd_regime_switching_grid_backtest import fetch_rates, initialize_mt5


ROOT = Path(__file__).resolve().parent
ART_V3 = ROOT / "artifacts_xauusd_regime_factor_research_v3"
ART_V3R = ROOT / "artifacts_xauusd_regime_factor_research_v3_regularized"
DEFAULT_CALENDAR_PATH = ROOT / "data" / "codex_native_calendar_majors.csv"
WIKI_API_URL = "https://en.wikipedia.org/w/api.php"
WIKI_HEADERS = {
    "User-Agent": "CodexRealtimeRegime/1.0 (local XAUUSD regime identifier)"
}


@dataclass
class ModelBundle:
    name: str
    features: list[str]
    bool_features: set[str]
    clip_bounds: dict[str, tuple[float, float]]
    mean_std: dict[str, tuple[float, float]]
    high_model: LogisticRegression
    trend_model: LogisticRegression
    regime_model: Ridge


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Realtime XAUUSD regime identifier based on V3R.")
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--timeframe", default="M15")
    parser.add_argument("--bars", type=int, default=12000)
    parser.add_argument("--terminal-path", default=r"C:\MT5PortableCodex\terminal64.exe")
    parser.add_argument(
        "--calendar-path",
        default=str(DEFAULT_CALENDAR_PATH),
    )
    parser.add_argument("--outdir", default="artifacts_xauusd_realtime_regime_identifier")
    parser.add_argument("--symbol-timezone", default="UTC")
    parser.add_argument("--loop", action="store_true", help="Run continuously instead of emitting one snapshot.")
    parser.add_argument("--interval-minutes", type=float, default=5.0, help="Refresh interval in minutes for loop mode.")
    parser.add_argument("--max-cycles", type=int, default=0, help="Optional max cycle count for testing. 0 means infinite.")
    parser.add_argument("--no-align", action="store_true", help="Do not align loop runs to wall-clock interval boundaries.")
    return parser.parse_args()


def load_selected_features() -> dict[str, list[str]]:
    rows = pd.read_csv(ART_V3 / "selected_features_v3.csv")
    return {
        str(row["model_group"]): [item for item in str(row["selected_features"]).split(",") if item]
        for _, row in rows.iterrows()
    }


def load_hyperparams(summary_name: str) -> dict[str, float]:
    df = pd.read_csv(ART_V3R / summary_name)
    return {
        "high_c": float(df.loc[df["model"].str.contains("high_vol"), "hyperparam"].iloc[0]),
        "trend_c": float(df.loc[df["model"].str.contains("trend_day"), "hyperparam"].iloc[0]),
        "regime_alpha": float(df.loc[df["model"].str.contains("regime_score"), "hyperparam"].iloc[0]),
    }


def is_bool_feature(feature: str) -> bool:
    return feature in {
        "OPEN_OUTSIDE_PREV_RANGE",
        "WEEKEND_GEO_CARRY",
        "london2h_break_prevday",
    }


def compute_standardization(frame: pd.DataFrame, features: list[str], bool_features: set[str]) -> tuple[dict[str, tuple[float, float]], dict[str, tuple[float, float]]]:
    mean_std: dict[str, tuple[float, float]] = {}
    clip_bounds: dict[str, tuple[float, float]] = {}
    for feature in features:
        series = frame[feature].astype(float)
        finite = series.replace([np.inf, -np.inf], np.nan).dropna()
        if finite.empty:
            mean_std[feature] = (0.0, 1.0)
            clip_bounds[feature] = (0.0, 0.0)
            continue
        if feature in bool_features:
            mean_std[feature] = (0.0, 1.0)
            clip_bounds[feature] = (0.0, 1.0)
        else:
            mean = float(finite.mean())
            std = float(finite.std())
            if not np.isfinite(std) or std == 0.0:
                std = 1.0
            mean_std[feature] = (mean, std)
            clip_bounds[feature] = (float(finite.min()), float(finite.max()))
    return mean_std, clip_bounds


def standardize_for_fit(frame: pd.DataFrame, features: list[str], bool_features: set[str], mean_std: dict[str, tuple[float, float]], clip_bounds: dict[str, tuple[float, float]]) -> pd.DataFrame:
    out = frame.copy()
    for feature in features:
        low, high = clip_bounds[feature]
        out[feature] = out[feature].astype(float).clip(lower=low, upper=high)
        if feature in bool_features:
            out[feature] = out[feature].astype(float)
            continue
        mean, std = mean_std[feature]
        out[feature] = (out[feature] - mean) / std
    return out


def fit_bundle(frame: pd.DataFrame, features: list[str], summary_name: str, bundle_name: str) -> ModelBundle:
    bool_features = {feature for feature in features if is_bool_feature(feature)}
    df = frame.loc[frame[features + ["high_vol_day", "trend_day", "regime_score"]].notna().all(axis=1)].copy()
    if df.empty:
        raise RuntimeError(f"No usable rows to fit bundle {bundle_name}")
    params = load_hyperparams(summary_name)
    mean_std, clip_bounds = compute_standardization(df, features, bool_features)
    train_std = standardize_for_fit(df, features, bool_features, mean_std, clip_bounds)

    high_model = LogisticRegression(C=params["high_c"], solver="liblinear", max_iter=5000, random_state=42)
    trend_model = LogisticRegression(C=params["trend_c"], solver="liblinear", max_iter=5000, random_state=42)
    regime_model = Ridge(alpha=params["regime_alpha"])

    high_model.fit(train_std[features], train_std["high_vol_day"].astype(int))
    trend_model.fit(train_std[features], train_std["trend_day"].astype(int))
    regime_model.fit(train_std[features], train_std["regime_score"].astype(float))
    return ModelBundle(
        name=bundle_name,
        features=features,
        bool_features=bool_features,
        clip_bounds=clip_bounds,
        mean_std=mean_std,
        high_model=high_model,
        trend_model=trend_model,
        regime_model=regime_model,
    )


def month_range(start_date: pd.Timestamp, end_date: pd.Timestamp) -> list[tuple[int, int]]:
    months = []
    current = pd.Timestamp(year=start_date.year, month=start_date.month, day=1)
    end_month = pd.Timestamp(year=end_date.year, month=end_date.month, day=1)
    while current <= end_month:
        months.append((int(current.year), int(current.month)))
        current = current + pd.offsets.MonthBegin(1)
    return months


def fetch_month_html_dynamic(year: int, month: int, cache_dir: Path) -> str:
    cache_path = cache_dir / f"wiki_current_events_{year}_{month:02d}.html"
    if cache_path.exists():
        return cache_path.read_text(encoding="utf-8")
    month_name = pd.Timestamp(year=year, month=month, day=1).strftime("%B")
    params = urlencode(
        {
            "action": "parse",
            "page": f"Portal:Current events/{month_name} {year}",
            "prop": "text",
            "format": "json",
        }
    )
    request = Request(f"{WIKI_API_URL}?{params}", headers=WIKI_HEADERS)
    try:
        with urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        insecure_context = ssl._create_unverified_context()
        with urlopen(request, timeout=60, context=insecure_context) as response:
            payload = json.loads(response.read().decode("utf-8"))
    html = payload["parse"]["text"]["*"]
    cache_path.write_text(html, encoding="utf-8")
    return html


def html_to_text(html: str) -> str:
    text = re.sub(r"</(li|p|div|h\d|ul|ol|table|tr)>", "\n", html, flags=re.I)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<.*?>", " ", text, flags=re.S)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_wiki_daily_texts_dynamic(start_date: pd.Timestamp, end_date: pd.Timestamp, cache_dir: Path) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    marker = re.compile(r'<span class="bday dtstart published updated itvstart">(\d{4}-\d{2}-\d{2})</span>')
    for year, month in month_range(start_date, end_date):
        html = fetch_month_html_dynamic(year, month, cache_dir)
        matches = list(marker.finditer(html))
        for idx, match in enumerate(matches):
            day = pd.Timestamp(match.group(1))
            if day < start_date or day > end_date:
                continue
            end_pos = matches[idx + 1].start() if idx + 1 < len(matches) else len(html)
            chunk = html[match.start() : end_pos]
            rows.append({"date": day, "wiki_text": html_to_text(chunk)})
    if not rows:
        return pd.DataFrame(columns=["date", "wiki_text"])
    return pd.DataFrame(rows).drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)


def build_macro_row_features(events: pd.DataFrame, start_date: pd.Timestamp, end_date: pd.Timestamp, outdir: Path) -> pd.DataFrame:
    daily_flags = build_macro_daily_flags(events, start_date, end_date, outdir)
    long_path = outdir / "macro_event_days_long.csv"
    if not long_path.exists():
        base = pd.DataFrame({"date": pd.date_range(start_date, end_date, freq="D")})
        return base
    long_df = pd.read_csv(long_path, parse_dates=["date"])
    pivot = long_df.pivot_table(index="date", columns="macro_family", values="event_rows", aggfunc="sum", fill_value=0)
    pivot.columns = [f"{col}_rows" for col in pivot.columns]
    pivot = pivot.reset_index()
    us_cols = [col for col in pivot.columns if col.startswith("US_")]
    if us_cols:
        pivot["usd_high_total_rows"] = pivot[us_cols].sum(axis=1)
    else:
        pivot["usd_high_total_rows"] = 0.0
    merged = daily_flags.merge(pivot, on="date", how="left")
    row_cols = [col for col in merged.columns if col.endswith("_rows")]
    for col in row_cols:
        merged[col] = merged[col].fillna(0.0)
    return merged


def add_weekend_geo_carry(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()

    def has_weekend(source_dates: str) -> bool:
        if not isinstance(source_dates, str) or not source_dates:
            return False
        for value in source_dates.split(","):
            stamp = pd.to_datetime(value, errors="coerce")
            if pd.isna(stamp):
                continue
            if stamp.weekday() >= 5:
                return True
        return False

    if "source_dates" not in out.columns:
        out["source_dates"] = ""
    out["WEEKEND_GEO_CARRY"] = out["source_dates"].apply(has_weekend)
    return out


def prepare_realtime_frames(raw_bars: pd.DataFrame, calendar_path: Path, outdir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    daily = build_daily_regime(raw_bars)
    daily = build_price_structure_features(daily)
    session = build_session_features(raw_bars)
    windows = build_open_window_features(raw_bars)

    base = daily.merge(session, on="date", how="left").merge(windows, on="date", how="left")
    base = base.sort_values("date").reset_index(drop=True)

    start_date = pd.Timestamp(base["date"].min())
    end_date = pd.Timestamp(base["date"].max())
    cross = build_cross_asset_features(start_date, end_date, outdir)
    proxies = build_proxy_features(start_date, end_date, outdir)

    full = base.merge(cross, on="date", how="left").merge(proxies, on="date", how="left")
    full = add_london_us_break_flags(add_intensity_features(full))

    events = load_native_calendar(calendar_path) if calendar_path.exists() else pd.DataFrame()
    if not events.empty:
        macro = build_macro_row_features(events, start_date, end_date, outdir)
    else:
        macro = pd.DataFrame({"date": pd.date_range(start_date, end_date, freq="D")})

    trading_dates = pd.Index(base["date"].sort_values().drop_duplicates())
    wiki_cache = outdir / "wiki_cache"
    wiki_cache.mkdir(parents=True, exist_ok=True)
    wiki_daily = extract_wiki_daily_texts_dynamic(start_date - pd.Timedelta(days=40), end_date, wiki_cache)
    if not wiki_daily.empty:
        geo_aligned = align_geo_dates_to_trading_days(wiki_daily, trading_dates)
        geo_flags, _ = build_geo_daily_flags(geo_aligned)
        geo_flags = add_weekend_geo_carry(geo_flags)
    else:
        geo_flags = pd.DataFrame({"date": trading_dates})
        geo_flags["WEEKEND_GEO_CARRY"] = False

    overlap = full.merge(macro, on="date", how="left").merge(geo_flags, on="date", how="left")
    overlap = add_geo_intensity(overlap)

    fill_false = [col for col in overlap.columns if col.endswith("_SHOCK") or col in {"GEO_ANY_SHOCK", "WEEKEND_GEO_CARRY"}]
    for col in fill_false:
        overlap[col] = overlap[col].fillna(False)
    fill_zero = [
        "FED_POLICY_rows",
        "US_INFLATION_rows",
        "usd_high_total_rows",
        "geo_total_score_z20_abs",
        "GEO_MIDDLE_EAST_score_z20_abs",
        "geo_total_score_z20_abs_lag1",
        "gold_vol_credit_intensity_lag1",
    ]
    for col in fill_zero:
        if col in overlap.columns:
            overlap[col] = overlap[col].fillna(0.0)

    lag_cols = [
        "dxy_abs_z20",
        "tnx_abs_z20",
        "vix_abs_z20",
        "oil_abs_z20",
        "spx_abs_z20",
        "geo_total_score_z20_abs",
        "GEO_MIDDLE_EAST_score_z20_abs",
        "gld_abs_z20",
        "gld_flow_proxy",
        "gc_volume_ratio20",
        "gvz_abs_z20",
        "jpy_ret",
        "gold_vol_credit_intensity",
    ]
    for frame in [full, overlap]:
        for col in lag_cols:
            if col in frame.columns:
                frame[f"{col}_lag1"] = frame[col].shift(1)

    return full.sort_values("date").reset_index(drop=True), overlap.sort_values("date").reset_index(drop=True)


def score_bundle(bundle: ModelBundle, row: pd.Series) -> dict[str, Any]:
    x = pd.DataFrame([{feature: row.get(feature, np.nan) for feature in bundle.features}], dtype=float)
    if x[bundle.features].isna().any(axis=None):
        missing = [feature for feature in bundle.features if pd.isna(x.at[0, feature])]
        raise ValueError(f"{bundle.name} missing features: {', '.join(missing)}")
    contribs = []
    for feature in bundle.features:
        value = float(x.at[0, feature])
        low, high = bundle.clip_bounds[feature]
        clipped = min(max(value, low), high)
        if feature in bundle.bool_features:
            standardized = clipped
        else:
            mean, std = bundle.mean_std[feature]
            standardized = (clipped - mean) / std
        x.at[0, feature] = standardized
        contribs.append(
            {
                "feature": feature,
                "value": value,
                "standardized": standardized,
            }
        )

    high_prob = float(bundle.high_model.predict_proba(x[bundle.features])[0, 1])
    trend_prob = float(bundle.trend_model.predict_proba(x[bundle.features])[0, 1])
    regime_score = float(bundle.regime_model.predict(x[bundle.features])[0])

    high_coefs = bundle.high_model.coef_[0]
    contributions = []
    for item, coef in zip(contribs, high_coefs):
        contributions.append(
            {
                "feature": item["feature"],
                "raw_value": item["value"],
                "standardized": item["standardized"],
                "high_vol_contribution": float(item["standardized"] * coef),
            }
        )
    contributions = sorted(contributions, key=lambda item: abs(item["high_vol_contribution"]), reverse=True)
    return {
        "high_vol_prob": high_prob,
        "trend_prob": trend_prob,
        "regime_score": regime_score,
        "top_contributions": contributions[:5],
    }


def classify_regime(high_prob: float, trend_prob: float, regime_score: float) -> str:
    if trend_prob >= 0.55 or (high_prob >= 0.65 and regime_score >= 1.15):
        return "TREND_EXPANSION"
    if high_prob >= 0.60:
        return "HIGH_VOLATILITY"
    if high_prob >= 0.45 or regime_score >= 0.95:
        return "TRANSITION"
    return "CALM_RANGE"


def determine_stage(current_date: pd.Timestamp, raw_bars: pd.DataFrame) -> dict[str, Any]:
    day_bars = raw_bars.loc[raw_bars["time"].dt.floor("D") == current_date].copy()
    london_bars = day_bars.loc[day_bars["time"].dt.hour.isin([8, 9])]
    us_bars = day_bars.loc[day_bars["time"].dt.hour.isin([16, 17])]
    return {
        "current_date": current_date,
        "latest_bar_time": day_bars["time"].max() if not day_bars.empty else pd.NaT,
        "london_ready": len(london_bars) >= 8,
        "us_ready": len(us_bars) >= 8,
    }


def build_snapshot(
    full_row: pd.Series,
    overlap_row: pd.Series,
    stage_info: dict[str, Any],
    bundles: dict[str, ModelBundle],
) -> dict[str, Any]:
    london_ready = bool(stage_info["london_ready"])
    us_ready = bool(stage_info["us_ready"])
    if us_ready:
        stage = "full_day_confirmed"
        struct_key = "full_explain"
        event_key = "overlap_explain"
    elif london_ready:
        stage = "london_confirmed"
        struct_key = "full_early"
        event_key = "overlap_early"
    else:
        stage = "overnight_prior"
        struct_key = "full_preopen"
        event_key = "overlap_preopen"

    structural = score_bundle(bundles[struct_key], full_row)
    event = score_bundle(bundles[event_key], overlap_row)

    event_weight = 0.35
    structural_weight = 0.65
    combined_high = structural_weight * structural["high_vol_prob"] + event_weight * event["high_vol_prob"]
    combined_trend = structural_weight * structural["trend_prob"] + event_weight * event["trend_prob"]
    combined_regime = structural_weight * structural["regime_score"] + event_weight * event["regime_score"]

    return {
        "stage": stage,
        "as_of_date": str(stage_info["current_date"].date()),
        "latest_bar_time_utc": None if pd.isna(stage_info["latest_bar_time"]) else str(pd.Timestamp(stage_info["latest_bar_time"])),
        "london_ready": london_ready,
        "us_ready": us_ready,
        "structural_model": structural,
        "event_model": event,
        "combined": {
            "high_vol_prob": combined_high,
            "trend_prob": combined_trend,
            "regime_score": combined_regime,
            "regime_label": classify_regime(combined_high, combined_trend, combined_regime),
        },
        "weights": {"structural": structural_weight, "event": event_weight},
    }


def snapshot_to_markdown(snapshot: dict[str, Any], outpath_json: Path) -> str:
    combined = snapshot["combined"]
    lines = [
        "# XAUUSD Realtime Regime Snapshot",
        "",
        f"- `stage`: `{snapshot['stage']}`",
        f"- `generated_at_utc`: `{snapshot['generated_at_utc']}`",
        f"- `as_of_date`: `{snapshot['as_of_date']}`",
        f"- `latest_bar_time_utc`: `{snapshot['latest_bar_time_utc']}`",
        f"- `london_ready`: `{snapshot['london_ready']}`",
        f"- `us_ready`: `{snapshot['us_ready']}`",
        f"- `regime_label`: `{combined['regime_label']}`",
        f"- `combined_high_vol_prob`: `{combined['high_vol_prob']:.3f}`",
        f"- `combined_trend_prob`: `{combined['trend_prob']:.3f}`",
        f"- `combined_regime_score`: `{combined['regime_score']:.3f}`",
        "",
        "## Structural Model",
        "",
        f"- `high_vol_prob`: `{snapshot['structural_model']['high_vol_prob']:.3f}`",
        f"- `trend_prob`: `{snapshot['structural_model']['trend_prob']:.3f}`",
        f"- `regime_score`: `{snapshot['structural_model']['regime_score']:.3f}`",
        "",
        "## Event Model",
        "",
        f"- `high_vol_prob`: `{snapshot['event_model']['high_vol_prob']:.3f}`",
        f"- `trend_prob`: `{snapshot['event_model']['trend_prob']:.3f}`",
        f"- `regime_score`: `{snapshot['event_model']['regime_score']:.3f}`",
        "",
        "## Top Structural Drivers",
        "",
    ]
    for item in snapshot["structural_model"]["top_contributions"]:
        lines.append(
            f"- `{item['feature']}`: raw `{item['raw_value']:.4f}`, contribution `{item['high_vol_contribution']:+.3f}`"
        )
    lines.extend(["", "## Top Event Drivers", ""])
    for item in snapshot["event_model"]["top_contributions"]:
        lines.append(
            f"- `{item['feature']}`: raw `{item['raw_value']:.4f}`, contribution `{item['high_vol_contribution']:+.3f}`"
        )
    lines.extend(["", f"- `json_snapshot`: `{outpath_json}`"])
    return "\n".join(lines)


def build_bundles() -> dict[str, ModelBundle]:
    selected = load_selected_features()
    full_hist = pd.read_csv(ART_V3 / "xau_regime_full_dataset_v3.csv", parse_dates=["date"])
    overlap_hist = pd.read_csv(ART_V3 / "xau_regime_overlap_dataset_v3.csv", parse_dates=["date"])

    bundles = {
        "full_explain": fit_bundle(full_hist, selected["full_explain"], "fullsample_model_summary_v3r.csv", "full_explain"),
        "overlap_explain": fit_bundle(overlap_hist, selected["overlap_explain"], "overlap_model_summary_v3r.csv", "overlap_explain"),
        "full_early": fit_bundle(full_hist, selected["full_early"], "fullsample_early_model_summary_v3r.csv", "full_early"),
        "overlap_early": fit_bundle(overlap_hist, selected["overlap_early"], "overlap_early_model_summary_v3r.csv", "overlap_early"),
    }
    preopen_full_features = [feature for feature in selected["full_early"] if feature not in {"london2h_range_ratio", "london2h_break_prevday"}]
    preopen_overlap_features = [feature for feature in selected["overlap_early"] if feature not in {"london2h_range_ratio", "london2h_break_prevday"}]
    bundles["full_preopen"] = fit_bundle(full_hist, preopen_full_features, "fullsample_early_model_summary_v3r.csv", "full_preopen")
    bundles["overlap_preopen"] = fit_bundle(overlap_hist, preopen_overlap_features, "overlap_early_model_summary_v3r.csv", "overlap_preopen")
    return bundles


def append_history(history_path: Path, snapshot: dict[str, Any]) -> None:
    with history_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(snapshot, ensure_ascii=False) + "\n")


def sleep_seconds_to_next_run(interval_minutes: float, align_to_clock: bool) -> float:
    interval_seconds = max(1.0, interval_minutes * 60.0)
    if not align_to_clock:
        return interval_seconds
    now = datetime.now()
    elapsed = now.minute * 60 + now.second + now.microsecond / 1_000_000
    remainder = elapsed % interval_seconds
    sleep_for = interval_seconds - remainder
    if sleep_for < 0.5:
        sleep_for += interval_seconds
    return sleep_for


def run_once(args: argparse.Namespace, bundles: dict[str, ModelBundle], outdir: Path) -> dict[str, Any]:
    initialize_mt5(args.terminal_path)
    try:
        raw_bars, point, contract_size = fetch_rates(args.symbol, args.timeframe, args.bars)
    finally:
        mt5.shutdown()

    full_live, overlap_live = prepare_realtime_frames(raw_bars, Path(args.calendar_path), outdir)
    current_date = pd.Timestamp(raw_bars["time"].dt.floor("D").max())
    full_row = full_live.loc[full_live["date"] == current_date].sort_values("date").iloc[-1]
    overlap_row = overlap_live.loc[overlap_live["date"] == current_date].sort_values("date").iloc[-1]
    stage_info = determine_stage(current_date, raw_bars)
    snapshot = build_snapshot(full_row, overlap_row, stage_info, bundles)
    snapshot["symbol"] = args.symbol
    snapshot["timeframe"] = args.timeframe
    snapshot["point"] = point
    snapshot["contract_size"] = contract_size
    snapshot["generated_at_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    json_path = outdir / "latest_regime_snapshot.json"
    md_path = outdir / "latest_regime_snapshot.md"
    history_path = outdir / "regime_snapshot_history.jsonl"
    json_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(snapshot_to_markdown(snapshot, json_path), encoding="utf-8")
    append_history(history_path, snapshot)

    print(f"Saved JSON: {json_path}")
    print(f"Saved Markdown: {md_path}")
    print(f"Appended History: {history_path}")
    print(
        f"Stage={snapshot['stage']} Label={snapshot['combined']['regime_label']} "
        f"HighVol={snapshot['combined']['high_vol_prob']:.3f} "
        f"Trend={snapshot['combined']['trend_prob']:.3f} "
        f"RegimeScore={snapshot['combined']['regime_score']:.3f}"
    )
    return snapshot


def main() -> None:
    args = parse_args()
    outdir = ROOT / args.outdir
    outdir.mkdir(parents=True, exist_ok=True)
    bundles = build_bundles()

    if not args.loop:
        run_once(args, bundles, outdir)
        return

    cycle = 0
    try:
        while True:
            cycle += 1
            print(f"[cycle {cycle}] running snapshot...")
            try:
                run_once(args, bundles, outdir)
            except Exception as exc:
                stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                print(f"[cycle {cycle}] error at {stamp} UTC: {exc}")
            if args.max_cycles > 0 and cycle >= args.max_cycles:
                break
            sleep_for = sleep_seconds_to_next_run(args.interval_minutes, align_to_clock=not args.no_align)
            wake_time = datetime.now() + timedelta(seconds=sleep_for)
            print(
                f"[cycle {cycle}] sleeping {sleep_for:.1f}s until "
                f"{wake_time.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            time.sleep(sleep_for)
    except KeyboardInterrupt:
        print("Loop stopped by user.")


if __name__ == "__main__":
    main()
