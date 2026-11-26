"""Populate a Deriv connection with a short, honest history through the public API.

A reviewer opening the trading terminal should see contracts, settlements, costs and a clickable
trade detail — not an empty table. This script drives the same endpoints a subscriber does, so
every row it creates has passed the execution gate and the risk engine, and is labelled with its
risk checks. It never writes to the database directly and never touches a real venue: point it at
a deployment whose API talks to the Deriv sandbox (`scripts/deriv_sandbox.py`).

Usage:
    VELTRANE_TESTER_PASSWORD='...' python -m scripts.seed_deriv_history \
        --base-url http://127.0.0.1:12001 --email elite@veltrane.dev

Refuses to run when the connection already has trades, so re-running is safe. Use --force to add
another batch anyway.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

DEFAULT_PASSWORD = "Veltrane!Test2026"

# Alternating sides and varied stakes, small enough that a $10,000 demo balance absorbs the losses
# without tripping the daily-loss or exposure rules the script is meant to respect.
BATCH = [
    ("R_100", "buy", 25.0),
    ("R_100", "sell", 30.0),
    ("frxEURUSD", "buy", 20.0),
    ("frxEURUSD", "sell", 35.0),
    ("R_100", "buy", 40.0),
    ("frxEURUSD", "buy", 15.0),
]


class ApiError(RuntimeError):
    def __init__(self, status: int, payload: object) -> None:
        super().__init__(f"HTTP {status}: {json.dumps(payload)[:400]}")
        self.status = status
        self.payload = payload


def call(base: str, method: str, path: str, token: str | None = None, body: dict | None = None) -> dict:
    request = urllib.request.Request(base.rstrip("/") + path, method=method)
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(request, data, timeout=30) as response:
            return json.loads(response.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            payload = json.loads(raw or "{}")
        except ValueError:
            payload = {"raw": raw[:400]}
        raise ApiError(exc.code, payload) from exc


def login(base: str, email: str, password: str) -> str:
    for attempt in range(10):
        try:
            return call(base, "POST", "/api/v1/auth/login", body={"email": email, "password": password})["access_token"]
        except ApiError as exc:
            if exc.status != 429:
                raise
            wait = 15
            print(f"  login rate limited, retrying in {wait}s ({attempt + 1}/10)", file=sys.stderr)
            time.sleep(wait)
    raise SystemExit("login stayed rate limited; wait a minute and run the script again")


def deriv_connection(base: str, token: str) -> dict:
    connections = call(base, "GET", "/api/v1/connections", token)["connections"]
    rows = [c for c in connections if c["provider"] == "deriv" and c["status"] != "revoked"]
    if not rows:
        raise SystemExit("no Deriv connection on this account; connect one first")
    return rows[0]


def already_seeded(base: str, token: str, connection_id: str) -> bool:
    contracts = call(base, "GET", f"/api/v1/deriv/connections/{connection_id}/contracts", token)
    return bool(contracts.get("contracts"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed a Deriv connection with demo history")
    parser.add_argument("--base-url", default=os.environ.get("VELTRANE_API_URL", "http://127.0.0.1:12001"))
    parser.add_argument("--email", default="elite@veltrane.dev")
    parser.add_argument("--force", action="store_true", help="seed another batch even if history exists")
    parser.add_argument(
        "--count",
        type=int,
        default=3,
        help="contracts to seed (kept at three so the consecutive-loss breaker stays disengaged)",
    )
    args = parser.parse_args(argv)

    password = os.environ.get("VELTRANE_TESTER_PASSWORD", DEFAULT_PASSWORD)
    base = args.base_url
    token = login(base, args.email, password)
    connection = deriv_connection(base, token)
    if connection.get("provider_account_type") != "demo":
        raise SystemExit(f"{connection['label']} is a real-money account; this script only seeds demo history")
    if not args.force and already_seeded(base, token, connection["id"]):
        print("Connection already has contract history; nothing to do (use --force to add more).")
        return 0

    print(f"Seeding {connection['label']} ({connection['provider_account_id']})")
    failures = 0
    for symbol, side, stake in BATCH[: args.count]:
        try:
            opened = call(
                base,
                "POST",
                f"/api/v1/deriv/connections/{connection['id']}/contracts",
                token,
                {"symbol": symbol, "side": side, "stake": stake, "duration": 5},
            )
        except ApiError as exc:
            failures += 1
            print(f"  {symbol} {side} {stake}: refused — {exc}")
            continue
        if not opened.get("approved"):
            failures += 1
            reasons = [f["message"] for f in (opened.get("risk") or {}).get("failed_rules", [])]
            print(f"  {symbol} {side} {stake}: rejected by the risk engine — {'; '.join(reasons)}")
            continue
        contract_id = opened.get("contract_id") or (opened.get("order") or {}).get("provider_order_id")
        print(f"  {symbol} {side} {stake}: opened contract {contract_id}")
        if not contract_id:
            failures += 1
            continue
        time.sleep(1)
        try:
            closed = call(
                base,
                "POST",
                f"/api/v1/deriv/connections/{connection['id']}/contracts/{contract_id}/close",
                token,
                {},
            )
        except ApiError as exc:
            failures += 1
            print(f"    close failed — {exc}")
            continue
        print(f"    settled at {closed.get('sold_for')} — {closed.get('message', 'settled')}")
        time.sleep(1)

    trades = call(base, "GET", "/api/v1/trades", token).get("trades", [])
    print(f"Done: {len(trades)} trades on the account, {failures} contract(s) not seeded.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
