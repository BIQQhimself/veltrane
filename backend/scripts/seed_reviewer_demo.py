"""Give the reviewer subscriber account something to look at, through the public API.

Connects a Deriv **demo** (sandbox) account, seeds three settled contracts, and leaves one paper
session running with a few ticks behind it. Everything goes through the endpoints a subscriber
uses, so each row carries its risk decision and its costs.

Usage:
    VELTRANE_REVIEWER_PASSWORD='...' python -m scripts.seed_reviewer_demo \
        --base-url http://127.0.0.1:12001 --token <sandbox PAT> --app-id <sandbox app id>

Idempotent: it reuses an existing Deriv connection and an existing paper session.
"""

from __future__ import annotations

import argparse
import os
import sys

from scripts import seed_deriv_history as history

DEFAULT_TOKEN = "pat_test_token_0123456789abcdef"
DEFAULT_APP_ID = "12345"


def derive_connection(base: str, token: str, api_key: str, app_id: str) -> dict:
    rows = history.call(base, "GET", "/api/v1/connections", token).get("connections", [])
    for row in rows:
        if row["provider"] == "deriv" and row["status"] != "revoked":
            return row
    connection = history.call(
        base,
        "POST",
        "/api/v1/connections",
        token,
        {
            "provider": "deriv",
            "label": "Deriv demo (sandbox)",
            "environment": "live",
            "api_key": api_key,
            "app_id": app_id,
        },
    )
    print(f"connected {connection['label']} ({connection.get('provider_account_id')})")
    return connection


def ensure_paper_session(base: str, token: str) -> None:
    sessions = history.call(base, "GET", "/api/v1/paper-sessions", token).get("sessions", [])
    running = [s for s in sessions if s.get("status") == "running"]
    if running:
        print(f"paper session already running ({running[0]['id'][:8]})")
        return
    session = history.call(
        base,
        "POST",
        "/api/v1/paper-sessions",
        token,
        {"strategy_code": "trend_following_v1", "symbol": "BTC/USDT", "timeframe": "1h"},
    )
    print(f"started paper session {session['id'][:8]} on {session['symbol']} {session['timeframe']}")
    for _ in range(3):
        history.call(base, "POST", f"/api/v1/paper-sessions/{session['id']}/tick", token, {})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed the reviewer subscriber's demo activity")
    parser.add_argument("--base-url", default=os.environ.get("VELTRANE_API_URL", "http://127.0.0.1:12001"))
    parser.add_argument("--email", default="reviewer@veltrane.dev")
    parser.add_argument("--token", default=os.environ.get("VELTRANE_DERIV_SANDBOX_TOKEN", DEFAULT_TOKEN))
    parser.add_argument("--app-id", default=os.environ.get("VELTRANE_DERIV_APP_ID", DEFAULT_APP_ID))
    args = parser.parse_args(argv)

    password = os.environ.get("VELTRANE_REVIEWER_PASSWORD", "Veltrane!Review2026")
    token = history.login(args.base_url, args.email, password)

    connection = derive_connection(args.base_url, token, args.token, args.app_id)
    if connection.get("provider_account_type") != "demo":
        raise SystemExit(f"{connection['label']} is a real-money account; refusing to seed it")

    # The history seeder reads its password from the environment, as it does when run by hand.
    os.environ["VELTRANE_TESTER_PASSWORD"] = password
    history.main(["--base-url", args.base_url, "--email", args.email])
    ensure_paper_session(args.base_url, token)

    summary = history.call(args.base_url, "GET", "/api/v1/portfolio/overview", token)
    print(
        f"portfolio: {summary.get('open_positions', 0)} open position(s), "
        f"equity {summary.get('equity')} {summary.get('currency', 'USD')}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
