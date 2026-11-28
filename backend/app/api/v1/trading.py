from __future__ import annotations

from app.api import serializers
from app.api.deps import get_current_user, get_or_404
from app.api.schemas import (
    ClosePositionRequest,
    KillSwitchRequest,
    LiveAuthorizationConfirm,
    LiveAuthorizationStart,
    OrderCreateRequest,
)
from app.core.config import settings
from app.core.errors import not_found
from app.core.rate_limit import enforce
from app.db.constants import KillScope
from app.db.models import Order, PaperSession, Position, RiskDecision, Trade, User
from app.db.session import get_db
from app.services import entitlements, kill_switch, live_authorization, platform_switch
from app.services.usage import get_usage
from app.trading import engine as trading_engine
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

router = APIRouter(tags=["trading"])


@router.post("/trading/paper-session", status_code=201)
def ensure_paper_session(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Idempotently provision the organisation's simulated account.

    New workspaces have no paper session until their first simulated order, which
    left the dashboard showing a zero balance with no way to start. This endpoint
    returns the running session or creates one with the configured starting balance.
    """
    session = trading_engine.paper_session_for(db, user, None)
    db.commit()
    return serializers.session_dict(session)


@router.post("/orders", status_code=201)
def create_order(
    payload: OrderCreateRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    enforce(request, "orders", limit=60, window=60)
    result = trading_engine.submit_order(
        db,
        user=user,
        request=trading_engine.OrderRequest(
            symbol=payload.symbol,
            side=payload.side,
            quantity=payload.quantity,
            order_type=payload.order_type,
            price=payload.price,
            stop_price=payload.stop_price,
            stop_loss=payload.stop_loss,
            take_profit=payload.take_profit,
            mode=payload.mode,
            connection_id=payload.connection_id,
            paper_session_id=payload.paper_session_id,
            strategy_version_id=payload.strategy_version_id,
            idempotency_key=payload.idempotency_key,
            reason=payload.reason,
        ),
        source="human",
    )
    order = result["order"]
    decision = result["decision"]
    fill = result.get("fill")
    return {
        "idempotent_replay": result.get("idempotent_replay", False),
        "order": serializers.order_dict(order, decision),
        "fill": (
            {
                "price": fill.price,
                "quantity": fill.filled_qty,
                "fee": fill.fee,
                "slippage_actual_bps": fill.slippage_actual_bps,
                "realized_pnl": fill.realized_pnl,
                "opened": fill.opened,
                "is_demo": order.is_demo,
            }
            if fill
            else None
        ),
        "trade": serializers.trade_dict(result["trade"]) if result.get("trade") else None,
        "disclaimer": (
            "Simulated execution. No real order was placed."
            if order.is_demo
            else "Live order routed to the venue. Verify on the exchange."
        ),
    }


@router.get("/orders")
def list_orders(
    mode: str | None = None, limit: int = 100, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    query = db.query(Order).filter(Order.org_id == user.org_id)
    if mode in ("paper", "live"):
        query = query.filter(Order.mode == mode)
    rows = query.order_by(Order.created_at.desc()).limit(min(limit, 300)).all()
    return {"orders": [serializers.order_dict(o) for o in rows]}


@router.get("/orders/{order_id}")
def get_order(order_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = get_or_404(db, Order, order_id)
    if order is None or order.org_id != user.org_id:
        raise not_found("order_not_found", "Order not found.")
    decision = db.get(RiskDecision, order.risk_decision_id) if order.risk_decision_id else None
    trade = db.query(Trade).filter(Trade.order_id == order.id).first()
    return {
        "order": serializers.order_dict(order, decision),
        "trade": serializers.trade_detail(db, trade) if trade else None,
    }


@router.post("/orders/{order_id}/cancel")
def cancel_order(order_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = get_or_404(db, Order, order_id)
    if order is None or order.org_id != user.org_id:
        raise not_found("order_not_found", "Order not found.")
    trading_engine.cancel_order(db, user=user, order=order)
    db.commit()
    return {"status": "canceled", "order_id": order.id}


@router.get("/trades")
def list_trades(
    mode: str | None = None,
    limit: int = 100,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Trade).filter(Trade.org_id == user.org_id)
    if mode in ("paper", "live"):
        query = query.filter(Trade.mode == mode)
    rows = query.order_by(Trade.closed_at.desc()).limit(min(limit, 300)).all()
    return {
        "trades": [serializers.trade_dict(t) for t in rows],
        "note": "Every row is clickable in the UI and opens a full, immutable detail view.",
    }


@router.get("/trades/{trade_id}")
def get_trade(trade_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    trade = get_or_404(db, Trade, trade_id)
    if trade is None or trade.org_id != user.org_id:
        raise not_found("trade_not_found", "Trade not found.")
    return {"trade": serializers.trade_detail(db, trade)}


@router.get("/positions")
def list_positions(status: str = "open", user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(Position).filter(Position.org_id == user.org_id)
    if status in ("open", "closed"):
        query = query.filter(Position.status == status)
    rows = query.order_by(Position.opened_at.desc()).limit(200).all()
    return {"positions": [serializers.position_dict(p) for p in rows]}


@router.post("/positions/{position_id}/close")
def close_position(
    position_id: str,
    payload: ClosePositionRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    position = get_or_404(db, Position, position_id)
    if position is None or position.org_id != user.org_id:
        raise not_found("position_not_found", "Position not found.")
    result = trading_engine.close_position(db, user=user, position=position, reason=payload.reason, note=payload.note)
    order = result["order"]
    return {
        "status": order.status,
        "order": serializers.order_dict(order, result.get("decision")),
        "trade": serializers.trade_dict(result["trade"]) if result.get("trade") else None,
        "human_intervention": True,
    }


@router.get("/trading/state")
def trading_state(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    session = (
        db.query(PaperSession)
        .filter(PaperSession.org_id == user.org_id, PaperSession.status == "running")
        .order_by(PaperSession.created_at.desc())
        .first()
    )
    positions = db.query(Position).filter(Position.org_id == user.org_id, Position.status == "open").all()
    return {
        "platform_live_enabled": platform_switch.effective(db),
        "kill_switches": kill_switch.state_for(db, user.org_id),
        "live": live_authorization.live_state(db, user.org_id),
        "paper_session": serializers.session_dict(session) if session else None,
        "open_positions": [serializers.position_dict(p) for p in positions],
        "demo_executions_today": int(get_usage(db, user.org_id, "demo_executions")),
        "executions_today": int(trading_engine.executions_today(db, user.org_id)),
        "daily_execution_cap": entitlements.daily_execution_cap(db, user.org_id),
        "data_source_mode": settings.market_data_source,
    }


@router.get("/trading/risk-budget")
def risk_budget(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Headroom left before the risk engine blocks new entries. Read-only."""
    return trading_engine.risk_budget(db, user)


@router.post("/trading/kill-switch")
def toggle_kill_switch(
    payload: KillSwitchRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.scope == KillScope.ORG:
        switch = kill_switch.engage(
            db,
            scope=KillScope.ORG,
            target=user.org_id,
            actor=user,
            reason=payload.reason,
            notify_org=user.org_id,
        )
    elif payload.scope == KillScope.PROVIDER:
        if not payload.target:
            from app.core.errors import bad_request

            raise bad_request("target_required", "Provider target is required.")
        switch = kill_switch.engage(
            db,
            scope=KillScope.PROVIDER,
            target=payload.target,
            actor=user,
            reason=payload.reason,
            notify_org=user.org_id,
        )
    else:
        switch = kill_switch.engage(
            db, scope=KillScope.USER, target=user.id, actor=user, reason=payload.reason, notify_org=user.org_id
        )

    flattened = None
    if payload.flatten:
        flattened = trading_engine.flatten_paper_positions(db, user=user, reason=f"Kill switch: {payload.reason}")
    db.commit()
    return {
        "status": "engaged",
        "scope": switch.scope,
        "target": switch.target,
        "engaged_at": serializers.iso(switch.engaged_at),
        "flattened": flattened,
        "notice": "New entries are blocked immediately. Exits remain available.",
    }


@router.post("/trading/kill-switch/release")
def release_kill_switch(
    payload: KillSwitchRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    target = user.org_id if payload.scope == KillScope.ORG else (payload.target or user.id)
    switch = kill_switch.release(db, scope=payload.scope, target=target, actor=user, reason=payload.reason)
    db.commit()
    return {"status": "released", "scope": switch.scope, "target": switch.target}


@router.post("/trading/live-authorization/start")
def start_live_authorization(
    payload: LiveAuthorizationStart,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    enforce(request, "live_auth", limit=5, window=3600)
    result = live_authorization.start_authorization(
        db,
        user=user,
        acknowledged=payload.acknowledged,
        checklist=payload.checklist,
        totp_code=payload.totp_code,
        jurisdiction=payload.jurisdiction,
        connection_id=payload.connection_id,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    return result


@router.post("/trading/live-authorization/confirm")
def confirm_live_authorization(
    payload: LiveAuthorizationConfirm,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    permission = live_authorization.confirm_authorization(
        db, user=user, token=payload.confirmation_token, ip=request.client.host if request.client else None
    )
    db.commit()
    return {
        "status": permission.status,
        "live_enabled": permission.live_enabled,
        "authorized_at": serializers.iso(permission.authorized_at),
        "platform_live_enabled": platform_switch.effective(db),
        "notice": (
            "Authorisation recorded. Live orders still require the operator to enable live trading "
            "and every order must pass the risk engine."
        ),
    }


@router.post("/trading/live-authorization/revoke")
def revoke_live_authorization(
    payload: ClosePositionRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    permission = live_authorization.revoke_authorization(db, user=user, reason=payload.reason)
    db.commit()
    return {"status": "revoked" if permission else "not_authorized"}
