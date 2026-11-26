from app.api.v1 import (
    admin,
    analytics,
    auth,
    billing,
    binary,
    connections,
    copilot,
    deriv,
    email,
    health,
    markets,
    notifications,
    portfolio,
    referrals,
    strategies,
    trading,
)
from fastapi import APIRouter

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(billing.router)
api_router.include_router(connections.router)
api_router.include_router(markets.router)
api_router.include_router(strategies.router)
api_router.include_router(trading.router)
api_router.include_router(binary.router)
api_router.include_router(deriv.router)
api_router.include_router(copilot.router)
api_router.include_router(portfolio.router)
api_router.include_router(analytics.router)
api_router.include_router(notifications.router)
api_router.include_router(email.router)
api_router.include_router(referrals.router)
api_router.include_router(admin.router)
