from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager

from app import __version__
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import configure_logging
from app.core.rate_limit import enforce
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import StatementError
from starlette.middleware.base import BaseHTTPMiddleware

configure_logging()
log = logging.getLogger("veltrane")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info(
        "startup",
        extra={
            "extra_fields": {
                "env": settings.env,
                "live_trading_enabled": settings.live_trading_enabled,
                "billing_provider": settings.billing_provider,
                "market_data_source": settings.market_data_source,
                "version": __version__,
            }
        },
    )
    if settings.live_trading_enabled:
        log.warning(
            "LIVE_TRADING_ENABLED",
            extra={"extra_fields": {"message": "Platform live execution is enabled. Every order still passes the risk engine."}},
        )
    yield
    log.info("shutdown")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api/") else response.headers.get("Cache-Control", "no-cache")
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


app = FastAPI(
    title="VELTRANE API",
    version=__version__,
    description=(
        "Multi-tenant AI trading SaaS API. Funds are never custodied. Live trading is disabled by default and "
        "requires explicit multi-step authorisation plus independent risk-engine approval."
    ),
    docs_url="/docs" if not settings.is_production else None,
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "X-Request-ID", "Stripe-Signature", "X-Mock-Signature", "X-Mock-Timestamp"],
    expose_headers=["X-Request-ID"],
    max_age=600,
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestContextMiddleware)


@app.middleware("http")
async def global_rate_limit(request: Request, call_next):
    if request.url.path.startswith("/api/"):
        try:
            enforce(request, "global", limit=600, window=60)
        except AppError as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    return await call_next(request)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "detail": {
                "code": "validation_error",
                "message": "Request validation failed.",
                "details": {"errors": [{"loc": e.get("loc"), "msg": e.get("msg")} for e in exc.errors()][:20]},
            }
        },
    )


@app.exception_handler(StatementError)
async def bad_identifier_handler(request: Request, exc: StatementError):
    log.warning("invalid_identifier", extra={"extra_fields": {"path": request.url.path}})
    return JSONResponse(
        status_code=400,
        content={"detail": {"code": "invalid_identifier", "message": "The request contained an invalid identifier.", "details": {}}},
    )


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception):
    log.exception("unhandled_error", extra={"extra_fields": {"path": request.url.path}})
    return JSONResponse(
        status_code=500,
        content={"detail": {"code": "internal_error", "message": "An unexpected error occurred. No sensitive details are exposed."}},
    )


app.include_router(api_router)


@app.get("/", include_in_schema=False)
def root():
    return {
        "service": "VELTRANE API",
        "version": __version__,
        "docs": "/docs" if not settings.is_production else None,
        "health": "/api/v1/health",
        "live_trading_enabled": settings.live_trading_enabled,
    }
