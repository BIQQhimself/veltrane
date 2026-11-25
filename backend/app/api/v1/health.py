from __future__ import annotations

from app import __version__
from app.core.config import settings
from app.db.models import Trade, User
from app.db.session import get_db
from app.providers.registry import provider_catalog
from app.services import market_data
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

router = APIRouter(tags=["system"])


@router.get("/health")
def health():
    return {"status": "ok", "version": __version__}


@router.get("/ready")
def ready(db: Session = Depends(get_db)):
    try:
        db.execute(text("select 1"))
        db_ok = True
    except Exception:  # noqa: BLE001
        db_ok = False
    return {
        "status": "ready" if db_ok else "degraded",
        "database": db_ok,
        "live_trading_enabled": settings.live_trading_enabled,
    }


@router.get("/config")
def public_config():
    """Non-secret runtime configuration the frontend needs to render honest labels."""
    return {
        "app_name": settings.app_name,
        "env": settings.env,
        "live_trading_enabled": settings.live_trading_enabled,
        "demo_market_data_enabled": settings.demo_market_data_enabled,
        "market_data_source": settings.market_data_source,
        "billing_provider": settings.billing_provider,
        "paper_costs": {
            "taker_fee_bps": settings.paper_taker_fee_bps,
            "spread_bps": settings.paper_spread_bps,
            "slippage_bps": settings.paper_slippage_bps,
            "starting_balance": settings.paper_starting_balance,
        },
        "disclaimer": (
            "VELTRANE does not custody funds and does not provide investment advice. Trading involves substantial "
            "risk of loss. Simulated results are not real trading results."
        ),
    }


@router.get("/status/summary")
def status_summary(db: Session = Depends(get_db)):
    return {
        "version": __version__,
        "providers": provider_catalog(),
        "instruments": len(market_data.supported_symbols()),
        "live_trading_enabled": settings.live_trading_enabled,
        "trades_recorded": db.query(Trade).count(),
        "users": db.query(User).count(),
    }
