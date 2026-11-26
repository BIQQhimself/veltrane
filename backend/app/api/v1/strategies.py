from __future__ import annotations

from app.api import serializers
from app.api.deps import get_current_user, get_or_404
from app.api.schemas import (
    BacktestRequest,
    PaperSessionRequest,
    StrategyApproveRequest,
    StrategyVersionRequest,
)
from app.core.errors import not_found
from app.db.models import Backtest, PaperSession, Position, StrategyVersion, Trade, User
from app.db.session import get_db
from app.services import strategy_service
from app.services.strategy_service import run_backtest as execute_backtest
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

router = APIRouter(tags=["strategies"])


@router.get("/strategies")
def list_strategies(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {
        "strategies": strategy_service.list_available(db, user.org_id),
        "disclaimer": (
            "Strategies are research tools, not investment advice. No strategy is claimed to be profitable. "
            "All backtests are net of modelled fees, spread, slippage and funding estimates."
        ),
    }


@router.get("/strategies/{code}")
def get_strategy(code: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    impl, version, record = strategy_service.resolve_strategy(db, user.org_id, code)
    return {
        "strategy": {
            "id": record.id,
            "code": record.code,
            "name": record.name,
            "category": record.category,
            "summary": record.summary,
            "version": version.version,
            "version_id": version.id,
            "status": version.status,
            "supported_markets": version.supported_markets,
            "timeframes": version.timeframes,
            "params_schema": version.params_schema,
            "default_params": version.default_params,
            "entry_rules": version.entry_rules,
            "exit_rules": version.exit_rules,
            "risk_params": version.risk_params,
            "data_requirements": version.data_requirements,
            "backtest_methodology": version.backtest_methodology,
            "known_limitations": version.known_limitations,
            "changelog": version.changelog,
        }
    }


@router.get("/strategies/{code}/versions")
def versions(code: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    impl, version, record = strategy_service.resolve_strategy(db, user.org_id, code)
    rows = (
        db.query(StrategyVersion)
        .filter(StrategyVersion.strategy_id == record.id)
        .order_by(StrategyVersion.version.desc())
        .all()
    )
    return {
        "versions": [
            {
                "id": v.id,
                "version": v.version,
                "status": v.status,
                "params": v.default_params,
                "changelog": v.changelog,
                "requires_approval": v.requires_approval,
                "approved_at": serializers.iso(v.approved_at),
                "created_at": serializers.iso(v.created_at),
            }
            for v in rows
        ]
    }


@router.post("/strategies/{code}/versions", status_code=201)
def create_version(
    code: str,
    payload: StrategyVersionRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    version = strategy_service.create_custom_version(
        db, user=user, code=code, params=payload.params, changelog=payload.changelog
    )
    db.commit()
    return {
        "version": {
            "id": version.id,
            "version": version.version,
            "status": version.status,
            "params": version.default_params,
            "changelog": version.changelog,
        },
        "notice": "Draft created. Approve it explicitly before it can trade.",
    }


@router.post("/strategies/versions/{version_id}/approve")
def approve_version(
    version_id: str,
    payload: StrategyApproveRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    version = strategy_service.approve_version(
        db, user=user, version_id=version_id, acknowledge_risk=payload.acknowledge_risk
    )
    db.commit()
    return {"status": version.status, "version_id": version.id, "approved_at": serializers.iso(version.approved_at)}


@router.post("/backtests", status_code=201)
def create_backtest(payload: BacktestRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    record = execute_backtest(
        db,
        user=user,
        code=payload.strategy_code,
        symbol=payload.symbol,
        timeframe=payload.timeframe,
        params=payload.params,
        start=payload.start,
        end=payload.end,
        with_walk_forward=payload.walk_forward,
    )
    db.commit()
    return serializers.backtest_dict(record, include_curve=True)


@router.get("/backtests")
def list_backtests(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (
        db.query(Backtest).filter(Backtest.org_id == user.org_id).order_by(Backtest.created_at.desc()).limit(100).all()
    )
    return {"backtests": [serializers.backtest_dict(b) for b in rows]}


@router.get("/backtests/{backtest_id}")
def get_backtest(backtest_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    record = get_or_404(db, Backtest, backtest_id)
    if record is None or record.org_id != user.org_id:
        raise not_found("backtest_not_found", "Backtest not found.")
    return serializers.backtest_dict(record, include_curve=True)


@router.get("/paper-sessions")
def list_sessions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (
        db.query(PaperSession)
        .filter(PaperSession.org_id == user.org_id)
        .order_by(PaperSession.created_at.desc())
        .limit(50)
        .all()
    )
    return {"sessions": [serializers.session_dict(s) for s in rows]}


@router.post("/paper-sessions", status_code=201)
def start_session(payload: PaperSessionRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    session = strategy_service.start_paper_session(
        db,
        user=user,
        code=payload.strategy_code,
        symbol=payload.symbol,
        timeframe=payload.timeframe,
        params=payload.params,
    )
    db.commit()
    return serializers.session_dict(session)


@router.post("/paper-sessions/{session_id}/tick")
def tick_session(session_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    session = get_or_404(db, PaperSession, session_id)
    if session is None or session.org_id != user.org_id:
        raise not_found("session_not_found", "Paper session not found.")
    return strategy_service.run_paper_tick(db, user=user, session=session)


@router.post("/paper-sessions/{session_id}/stop")
def stop_session(session_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    session = get_or_404(db, PaperSession, session_id)
    if session is None or session.org_id != user.org_id:
        raise not_found("session_not_found", "Paper session not found.")
    result = strategy_service.stop_paper_session(db, user=user, session=session)
    db.commit()
    return serializers.session_dict(result)


@router.get("/paper-sessions/{session_id}")
def session_detail(session_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    session = get_or_404(db, PaperSession, session_id)
    if session is None or session.org_id != user.org_id:
        raise not_found("session_not_found", "Paper session not found.")
    positions = db.query(Position).filter(Position.paper_session_id == session.id).all()
    trades = (
        db.query(Trade).filter(Trade.paper_session_id == session.id).order_by(Trade.closed_at.desc()).limit(100).all()
    )
    return {
        "session": serializers.session_dict(session),
        "positions": [serializers.position_dict(p) for p in positions],
        "trades": [serializers.trade_dict(t) for t in trades],
        "disclaimer": "All activity here is simulated. No order reached a real venue.",
    }
