from __future__ import annotations

from datetime import UTC, datetime

from app.db.models import PaperSession, Trade

BASE = "/api/v1"


def _session(client, account) -> dict:
    return client.post(f"{BASE}/trading/paper-session", headers=account["headers"]).json()


def test_risk_budget_is_read_only_and_reports_every_control(client, trader):
    session = _session(client, trader)
    before = session["equity"]

    response = client.get(f"{BASE}/trading/risk-budget", headers=trader["headers"])

    assert response.status_code == 200, response.text
    body = response.json()
    labels = {budget["label"] for budget in body["budgets"]}
    assert {
        "Daily loss",
        "Drawdown",
        "Account exposure",
        "Open positions",
        "Consecutive losses",
        "Demo executions today",
    } <= labels
    assert body["state"] == "ok"
    assert body["blocked"] == []
    assert body["equity"] == before
    state = client.get(f"{BASE}/trading/state", headers=trader["headers"]).json()
    assert state["paper_session"]["equity"] == before


def test_risk_budget_requires_authentication(client):
    assert client.get(f"{BASE}/trading/risk-budget").status_code == 401


def test_risk_budget_flags_a_spent_daily_loss_allowance(client, db, trader):
    session = _session(client, trader)
    row = db.get(PaperSession, session["id"])
    # Equity 1,000 with a 3% daily-loss cap allows a 30 loss. Record 40 of realised loss.
    row.equity = 1000
    row.cash_balance = 1000
    db.add(
        Trade(
            org_id=row.org_id,
            paper_session_id=row.id,
            instrument_symbol="BTC/USDT",
            side="long",
            quantity=1,
            entry_price=100,
            exit_price=60,
            notional=100,
            gross_pnl=-40,
            net_pnl=-40,
            fees=0,
            is_demo=True,
            mode="paper",
            opened_at=datetime.now(UTC),
            closed_at=datetime.now(UTC),
        )
    )
    db.commit()

    body = client.get(f"{BASE}/trading/risk-budget", headers=trader["headers"]).json()

    daily = next(budget for budget in body["budgets"] if budget["label"] == "Daily loss")
    assert daily["state"] == "blocked"
    assert daily["used"] == 40
    assert daily["cap"] == 30
    assert daily["remaining"] == 0
    assert "Daily loss" in body["blocked"]
    assert body["state"] == "blocked"


def test_risk_budget_reflects_the_kill_switch(client, trader):
    engaged = client.post(
        f"{BASE}/trading/kill-switch",
        json={"scope": "org", "reason": "operator test"},
        headers=trader["headers"],
    )
    assert engaged.status_code == 200, engaged.text

    body = client.get(f"{BASE}/trading/risk-budget", headers=trader["headers"]).json()

    assert body["kill_switches"]["org"] is True
    assert "Kill switch" in body["blocked"]


def test_risk_budget_is_tenant_scoped(client, db, trader, trader2):
    mine = _session(client, trader)
    row = db.get(PaperSession, mine["id"])
    row.equity = 1000
    row.cash_balance = 1000
    db.commit()

    mine_body = client.get(f"{BASE}/trading/risk-budget", headers=trader["headers"]).json()
    theirs_body = client.get(f"{BASE}/trading/risk-budget", headers=trader2["headers"]).json()

    assert mine_body["equity"] == 1000
    assert theirs_body["equity"] != 1000
