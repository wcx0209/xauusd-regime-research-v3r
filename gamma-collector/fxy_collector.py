"""Create an hourly USD/JPY gamma proxy from the free FXY option chain."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yfinance as yf

from collector import bs_gamma, last_price, retry, risk_free_rate, rows_to_contracts


MAX_DAYS = 120
MAX_EXPIRIES = 7
STRIKE_STEP_USDJPY = 0.25


def round_usdjpy(value: float) -> float:
    return round(value / STRIKE_STEP_USDJPY) * STRIKE_STEP_USDJPY


def load_fxy_chain(now: datetime):
    ticker = yf.Ticker("FXY")
    fxy_spot = last_price("FXY")
    usdjpy_spot = last_price("JPY=X")
    all_expiries = retry(lambda: list(ticker.options))
    cutoff = now.date() + timedelta(days=MAX_DAYS)
    expiries = [value for value in all_expiries if now.date() <= date.fromisoformat(value) <= cutoff][:MAX_EXPIRIES]
    if not expiries:
        raise RuntimeError("Yahoo returned no usable FXY expiries")

    contracts = []
    loaded_expiries = []
    for expiry in expiries:
        try:
            chain = retry(lambda expiry=expiry: ticker.option_chain(expiry))
        except Exception as exc:
            print(f"warning: skipped {expiry}: {exc}")
            continue
        expiry_contracts = rows_to_contracts(chain.calls, "call", expiry, now)
        expiry_contracts += rows_to_contracts(chain.puts, "put", expiry, now)
        if expiry_contracts:
            contracts.extend(expiry_contracts)
            loaded_expiries.append(expiry)
    if not contracts:
        raise RuntimeError("Yahoo returned no usable FXY contracts")
    return fxy_spot, usdjpy_spot, loaded_expiries, contracts


def build_payload(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    fxy_spot, usdjpy_spot, expiries, contracts = load_fxy_chain(now)
    rate = risk_free_rate()
    buckets = defaultdict(lambda: {"call_oi": 0.0, "put_oi": 0.0, "call_gamma_oi": 0.0, "put_gamma_oi": 0.0})

    for contract in contracts:
        mapped_strike = round_usdjpy(usdjpy_spot * fxy_spot / contract.strike)
        key = (contract.expiry, mapped_strike)
        gamma = bs_gamma(fxy_spot, contract.strike, contract.iv, contract.years, rate)
        oi_key = f"{contract.option_type}_oi"
        gamma_key = f"{contract.option_type}_gamma_oi"
        buckets[key][oi_key] += contract.open_interest
        buckets[key][gamma_key] += gamma * contract.open_interest

    rows = []
    for (expiry, strike), values in sorted(buckets.items()):
        call_oi = values["call_oi"]
        put_oi = values["put_oi"]
        rows.append(
            {
                "strike": strike,
                "call_oi": round(call_oi),
                "put_oi": round(put_oi),
                "call_gamma": values["call_gamma_oi"] / call_oi if call_oi else 0.0,
                "put_gamma": values["put_gamma_oi"] / put_oi if put_oi else 0.0,
                "expiry": expiry,
            }
        )

    net_proxy = sum(row["call_gamma"] * row["call_oi"] - row["put_gamma"] * row["put_oi"] for row in rows)
    return {
        "asOf": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source": "yfinance_FXY_chain:call_plus_put_minus_proxy",
        "proxySymbol": "FXY",
        "fxyPrice": round(fxy_spot, 4),
        "usdJpyPrice": round(usdjpy_spot, 4),
        "expiries": expiries,
        "contractRows": len(rows),
        "netGammaProxy": net_proxy,
        "rows": rows,
    }


def write_outputs(payload: dict, output: Path, history: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    history.parent.mkdir(parents=True, exist_ok=True)
    exists = history.exists()
    summary = {key: payload[key] for key in ["asOf", "source", "fxyPrice", "usdJpyPrice", "contractRows", "netGammaProxy"]}
    with history.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary))
        if not exists:
            writer.writeheader()
        writer.writerow(summary)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--history", type=Path)
    args = parser.parse_args()
    payload = build_payload()
    if args.dry_run or not args.output:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    if args.output:
        if not args.history:
            raise RuntimeError("--history is required when --output is used")
        write_outputs(payload, args.output, args.history)
        print(json.dumps({"ok": True, "asOf": payload["asOf"], "rows": payload["contractRows"]}))


if __name__ == "__main__":
    main()

