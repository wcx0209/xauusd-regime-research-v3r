"""Build GLD option-chain gamma levels and send hourly aggregates to the dashboard.

This is an open-interest/Black-Scholes proxy. Yahoo does not publish dealer books,
trade direction, or contract-level gamma, so calls are assigned positive GEX and
puts negative GEX as a documented modelling assumption.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import time
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, time as clock_time, timedelta, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd
import yfinance as yf


CONTRACT_MULTIPLIER = 100.0
MAX_DAYS = 90
MAX_EXPIRIES = 8
MIN_EXPIRIES = 2
GRID_POINTS = 121
GOLD_API_URL = "https://api.gold-api.com/price/XAU"


@dataclass(frozen=True)
class Contract:
    option_type: str
    strike: float
    iv: float
    open_interest: float
    years: float
    expiry: str
    bid: float
    ask: float
    last_price: float


def normal_pdf(value: float) -> float:
    return math.exp(-0.5 * value * value) / math.sqrt(2.0 * math.pi)


def bs_gamma(spot: float, strike: float, iv: float, years: float, rate: float) -> float:
    if min(spot, strike, iv, years) <= 0:
        return 0.0
    root_t = math.sqrt(years)
    d1 = (math.log(spot / strike) + (rate + 0.5 * iv * iv) * years) / (iv * root_t)
    return normal_pdf(d1) / (spot * iv * root_t)


def signed_gex(contract: Contract, spot: float, rate: float) -> float:
    gamma = bs_gamma(spot, contract.strike, contract.iv, contract.years, rate)
    dollar_gamma_1pct = gamma * contract.open_interest * CONTRACT_MULTIPLIER * spot * spot * 0.01
    return dollar_gamma_1pct if contract.option_type == "call" else -dollar_gamma_1pct


def retry(operation, attempts: int = 3):
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return operation()
        except Exception as exc:  # yfinance raises several transport exception types
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"Market data request failed after {attempts} attempts: {last_error}")


def last_price(symbol: str) -> float:
    def fetch() -> float:
        frame = yf.Ticker(symbol).history(period="5d", interval="1d", auto_adjust=False)
        closes = frame["Close"].dropna()
        if closes.empty:
            raise RuntimeError(f"No price returned for {symbol}")
        return float(closes.iloc[-1])

    return retry(fetch)


def gold_api_price() -> float:
    def fetch() -> float:
        request = urllib.request.Request(
            GOLD_API_URL,
            headers={"Accept": "application/json", "User-Agent": "GammaRadarCollector/1.0"},
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.load(response)
        price = float(payload.get("price", 0.0))
        if not math.isfinite(price) or price <= 0:
            raise RuntimeError("Gold API returned no valid XAU price")
        return price

    return retry(fetch)


def risk_free_rate() -> float:
    try:
        value = last_price("^IRX") / 100.0
        return value if 0.0 <= value <= 0.25 else 0.04
    except Exception:
        return 0.04


def years_to_expiry(expiry: str, now: datetime) -> float:
    expiry_date = date.fromisoformat(expiry)
    expiry_close = datetime.combine(expiry_date, clock_time(21, 0), tzinfo=timezone.utc)
    return max((expiry_close - now).total_seconds() / (365.25 * 86_400), 1.0 / (365.25 * 24))


def number(row: pd.Series, key: str, default: float = 0.0) -> float:
    value = row.get(key, default)
    return default if pd.isna(value) else float(value)


def rows_to_contracts(frame: pd.DataFrame, option_type: str, expiry: str, now: datetime) -> list[Contract]:
    years = years_to_expiry(expiry, now)
    contracts: list[Contract] = []
    for _, row in frame.iterrows():
        strike = number(row, "strike")
        iv = number(row, "impliedVolatility")
        oi = number(row, "openInterest")
        if strike <= 0 or not 0.01 <= iv <= 5.0 or oi <= 0:
            continue
        contracts.append(
            Contract(
                option_type=option_type,
                strike=strike,
                iv=iv,
                open_interest=oi,
                years=years,
                expiry=expiry,
                bid=number(row, "bid"),
                ask=number(row, "ask"),
                last_price=number(row, "lastPrice"),
            )
        )
    return contracts


def load_chain(now: datetime) -> tuple[float, list[str], list[Contract]]:
    ticker = yf.Ticker("GLD")
    spot = last_price("GLD")
    all_expiries = retry(lambda: list(ticker.options))
    cutoff = now.date() + timedelta(days=MAX_DAYS)
    expiries = [value for value in all_expiries if now.date() <= date.fromisoformat(value) <= cutoff][:MAX_EXPIRIES]
    if not expiries:
        raise RuntimeError("Yahoo returned no GLD expiries inside the configured window")

    contracts: list[Contract] = []
    loaded_expiries: list[str] = []
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
        raise RuntimeError("Yahoo returned no usable GLD contracts")
    if len(loaded_expiries) < MIN_EXPIRIES:
        raise RuntimeError(
            f"Yahoo returned only {len(loaded_expiries)} usable GLD expiry; preserving the previous snapshot"
        )
    return spot, loaded_expiries, contracts


def rank_walls(contracts: Iterable[Contract], spot: float, rate: float, option_type: str) -> list[float]:
    totals: dict[float, float] = {}
    for contract in contracts:
        if contract.option_type != option_type:
            continue
        if option_type == "call" and contract.strike <= spot:
            continue
        if option_type == "put" and contract.strike >= spot:
            continue
        totals[contract.strike] = totals.get(contract.strike, 0.0) + abs(signed_gex(contract, spot, rate))
    return [strike for strike, _ in sorted(totals.items(), key=lambda item: item[1], reverse=True)]


def gamma_flip(contracts: list[Contract], spot: float, rate: float) -> float:
    grid = [spot * (0.85 + 0.30 * index / (GRID_POINTS - 1)) for index in range(GRID_POINTS)]
    totals = [sum(signed_gex(contract, level, rate) for contract in contracts) for level in grid]
    crossings: list[float] = []
    for index in range(1, len(grid)):
        left, right = totals[index - 1], totals[index]
        if left == 0:
            crossings.append(grid[index - 1])
        elif left * right < 0:
            weight = abs(left) / (abs(left) + abs(right))
            crossings.append(grid[index - 1] + weight * (grid[index] - grid[index - 1]))
    if crossings:
        return min(crossings, key=lambda value: abs(value - spot))
    return grid[min(range(len(grid)), key=lambda index: abs(totals[index]))]


def expected_move(contracts: list[Contract], spot: float, front_expiry: str) -> float:
    front = [contract for contract in contracts if contract.expiry == front_expiry]
    strikes = sorted({contract.strike for contract in front})
    atm = min(strikes, key=lambda strike: abs(strike - spot))

    def premium(option_type: str) -> float:
        matches = [contract for contract in front if contract.option_type == option_type and contract.strike == atm]
        if not matches:
            return 0.0
        contract = matches[0]
        if contract.bid > 0 and contract.ask >= contract.bid:
            return (contract.bid + contract.ask) / 2.0
        return max(contract.last_price, 0.0)

    straddle = premium("call") + premium("put")
    if straddle > 0:
        return straddle
    atm_contracts = [contract for contract in front if contract.strike == atm]
    atm_iv = sum(contract.iv for contract in atm_contracts) / len(atm_contracts)
    return spot * atm_iv * math.sqrt(atm_contracts[0].years)


def build_payload(now: datetime | None = None) -> dict[str, object]:
    now = now or datetime.now(timezone.utc)
    spot, expiries, contracts = load_chain(now)
    xau_proxy = gold_api_price()
    rate = risk_free_rate()
    current = [(contract, signed_gex(contract, spot, rate)) for contract in contracts]
    per_strike: dict[float, float] = {}
    distribution: dict[float, dict[str, float]] = {}
    for contract, gex in current:
        per_strike[contract.strike] = per_strike.get(contract.strike, 0.0) + gex
        row = distribution.setdefault(
            contract.strike,
            {"callGex": 0.0, "putGex": 0.0, "callOi": 0.0, "putOi": 0.0},
        )
        row[f"{contract.option_type}Gex"] += gex
        row[f"{contract.option_type}Oi"] += contract.open_interest

    call_walls = rank_walls(contracts, spot, rate, "call")
    put_walls = rank_walls(contracts, spot, rate, "put")
    if not call_walls or not put_walls:
        raise RuntimeError("Could not identify both an out-of-the-money call wall and put wall")

    front_expiry = expiries[0]
    true_0dte = front_expiry == now.date().isoformat()
    front_gamma = sum(gex for contract, gex in current if contract.expiry == front_expiry)
    source = (
        f"yfinance_GLD_chain:dealer_sign_proxy;front={front_expiry};"
        f"front_label={'0dte' if true_0dte else 'nearest'};expiries={len(expiries)};xau=gold_api"
    )
    visible_distribution = [
        {
            "strike": round(strike, 4),
            "callGex": round(values["callGex"], 2),
            "putGex": round(values["putGex"], 2),
            "netGex": round(values["callGex"] + values["putGex"], 2),
            "callOi": round(values["callOi"]),
            "putOi": round(values["putOi"]),
        }
        for strike, values in distribution.items()
        if spot * 0.85 <= strike <= spot * 1.15
    ]
    visible_distribution = sorted(
        sorted(
            visible_distribution,
            key=lambda row: abs(row["callGex"]) + abs(row["putGex"]),
            reverse=True,
        )[:36],
        key=lambda row: row["strike"],
    )
    return {
        "asOf": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source": source,
        "xauPrice": round(xau_proxy, 4),
        "gldPrice": round(spot, 4),
        "netGamma0dte": round(front_gamma, 2),
        "netGammaAll": round(sum(gex for _, gex in current), 2),
        "expectedMoveGld": round(expected_move(contracts, spot, front_expiry), 4),
        "gammaFlip": round(gamma_flip(contracts, spot, rate), 4),
        "gammaPin": round(max(per_strike, key=lambda strike: abs(per_strike[strike])), 4),
        "callWall": round(call_walls[0], 4),
        "putWall": round(put_walls[0], 4),
        "secondCallWall": round(call_walls[1], 4) if len(call_walls) > 1 else None,
        "secondPutWall": round(put_walls[1], 4) if len(put_walls) > 1 else None,
        "distribution": visible_distribution,
    }


def write_outputs(payload: dict[str, object], output: Path, history: Path, distribution: Path) -> None:
    aggregate = {key: value for key, value in payload.items() if key != "distribution"}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(aggregate, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    distribution.parent.mkdir(parents=True, exist_ok=True)
    distribution.write_text(
        json.dumps(
            {
                "asOf": payload["asOf"],
                "source": payload["source"],
                "gldPrice": payload["gldPrice"],
                "xauPrice": payload["xauPrice"],
                "rows": payload["distribution"],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    history.parent.mkdir(parents=True, exist_ok=True)
    exists = history.exists()
    with history.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(aggregate))
        if not exists:
            writer.writeheader()
        writer.writerow(aggregate)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="calculate and print without uploading")
    parser.add_argument("--output", type=Path, help="write the latest aggregate as JSON")
    parser.add_argument("--history", type=Path, help="append the aggregate to a CSV history")
    parser.add_argument("--distribution", type=Path, help="write strike-by-strike GEX as JSON")
    args = parser.parse_args()
    payload = build_payload()
    if args.dry_run or not args.output:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    if args.output:
        if not args.history or not args.distribution:
            raise RuntimeError("--history and --distribution are required when --output is used")
        write_outputs(payload, args.output, args.history, args.distribution)
        print(json.dumps({"ok": True, "asOf": payload["asOf"], "source": payload["source"]}))


if __name__ == "__main__":
    main()

