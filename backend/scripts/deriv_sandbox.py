"""Run the Deriv protocol mock as a standalone gateway for local/staging review.

Deriv's account and execution endpoints need a Personal Access Token that only the account
owner can mint, so a reviewer cannot exercise the connect/trade flow against Deriv itself.
This script serves the same mock the test suite uses, so the whole path — token validation,
OTP socket, proposal, buy, close — can be walked end to end. It is *not* Deriv: every response
the API returns while ``VELTRANE_DERIV_SANDBOX=true`` is labelled ``sandbox``.

Usage:
    python -m scripts.deriv_sandbox --port 12003

Then run the API with:
    VELTRANE_DERIV_SANDBOX=true \
    VELTRANE_DERIV_REST_BASE=http://127.0.0.1:12003 \
    VELTRANE_DERIV_PUBLIC_WS_URL=ws://127.0.0.1:12003/trading/v1/options/ws/public \
    VELTRANE_DERIV_APP_ID=12345 \
    python -m uvicorn app.main:app
"""

from __future__ import annotations

import argparse
import sys

import uvicorn

sys.path.insert(0, "tests")

from tests.support.deriv_mock import MockState, create_app  # noqa: E402

SANDBOX_TOKEN = "pat_test_token_0123456789abcdef"
SANDBOX_APP_ID = "12345"


def main() -> int:
    parser = argparse.ArgumentParser(description="Deriv protocol mock gateway")
    parser.add_argument("--port", type=int, default=12003)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    state = MockState(token=SANDBOX_TOKEN, app_id=SANDBOX_APP_ID)
    app = create_app(state)
    print(
        "Deriv sandbox gateway on "
        f"http://{args.host}:{args.port}\n"
        f"  token: {SANDBOX_TOKEN}\n"
        f"  app id: {SANDBOX_APP_ID}\n"
        "  accounts: VRTC900001 (demo, 10000 USD), CR700001 (real, 250 USD)\n"
        "  Sandbox only. No request leaves this process."
    )
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning", lifespan="off")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
