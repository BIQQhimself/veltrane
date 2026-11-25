from __future__ import annotations

from app.api import serializers
from app.api.deps import get_current_user
from app.api.schemas import (
    CancelSubscriptionRequest,
    ChangePlanRequest,
    CheckoutRequest,
    ConsentRequest,
    MockCompleteRequest,
)
from app.core.errors import not_found
from app.core.rate_limit import enforce
from app.db.models import Invoice, Payment, Plan, Refund, User
from app.db.session import get_db
from app.services import billing, entitlements
from app.services.entitlements import active_subscription
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

router = APIRouter(tags=["billing"])


@router.get("/plans")
def list_plans(db: Session = Depends(get_db)):
    plans = db.query(Plan).filter(Plan.is_active.is_(True)).order_by(Plan.sort_order).all()
    return {
        "plans": [
            {
                "code": p.code,
                "name": p.name,
                "tagline": p.tagline,
                "price_monthly": float(p.price_monthly),
                "currency": p.currency,
                "features": p.features,
                "limits": p.limits,
                "trial_days": p.trial_days,
                "is_active": p.is_active,
            }
            for p in plans
        ],
        "note": "Live trading requires explicit authorisation and a platform-level enablement, regardless of plan.",
    }


@router.get("/billing/subscription")
def get_subscription(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    sub = active_subscription(db, user.org_id)
    ent = entitlements.resolve_entitlements(db, user.org_id)
    return {
        "subscription": (
            {
                "id": sub.id,
                "plan_code": sub.plan_code,
                "status": sub.status,
                "provider": sub.provider,
                "current_period_start": serializers.iso(sub.current_period_start),
                "current_period_end": serializers.iso(sub.current_period_end),
                "cancel_at_period_end": sub.cancel_at_period_end,
                "canceled_at": serializers.iso(sub.canceled_at),
                "trial_end": serializers.iso(sub.trial_end),
                "pending_plan_code": sub.pending_plan_code,
                "pending_effective_at": serializers.iso(sub.pending_effective_at),
            }
            if sub
            else None
        ),
        "effective_plan_code": ent["plan_code"],
        "entitlements": ent,
    }


@router.post("/billing/checkout")
def checkout(payload: CheckoutRequest, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    enforce(request, "checkout", limit=10, window=600)
    result = billing.create_checkout(db, org=user.org_id, plan_code=payload.plan_code, user=user)
    db.commit()
    return {
        **result,
        "notice": (
            "Mock provider: complete the simulated payment to exercise the signed webhook path."
            if result.get("mode") == "mock"
            else "Redirect the user to checkout_url. Entitlements change only after the verified webhook."
        ),
    }


@router.post("/billing/mock/complete")
def mock_complete(payload: MockCompleteRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    result = billing.complete_mock_checkout(db, payload.checkout_token)
    db.commit()
    return {
        **result,
        "notice": "Mock provider only. In production a signed provider webhook performs this transition.",
    }


@router.post("/billing/change-plan")
def change_plan(payload: ChangePlanRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    result = billing.change_plan(db, org_id=user.org_id, user=user, new_plan_code=payload.plan_code)
    db.commit()
    return result


@router.post("/billing/cancel")
def cancel(payload: CancelSubscriptionRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    sub = billing.cancel_subscription(db, org_id=user.org_id, user=user, immediate=payload.immediate)
    db.commit()
    return {"status": sub.status, "cancel_at_period_end": sub.cancel_at_period_end, "plan_code": sub.plan_code}


@router.get("/billing/invoices")
def invoices(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Invoice).filter(Invoice.org_id == user.org_id).order_by(Invoice.created_at.desc()).limit(100).all()
    return {
        "invoices": [
            {
                "id": i.id,
                "number": i.number,
                "subtotal": float(i.subtotal),
                "tax": float(i.tax),
                "total": float(i.total),
                "currency": i.currency,
                "status": i.status,
                "period_start": serializers.iso(i.period_start),
                "period_end": serializers.iso(i.period_end),
                "paid_at": serializers.iso(i.paid_at),
                "line_items": i.line_items,
                "created_at": serializers.iso(i.created_at),
            }
            for i in rows
        ]
    }


@router.get("/billing/payments")
def payments(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Payment).filter(Payment.org_id == user.org_id).order_by(Payment.created_at.desc()).limit(100).all()
    refunds = db.query(Refund).filter(Refund.org_id == user.org_id).order_by(Refund.created_at.desc()).limit(100).all()
    return {
        "payments": [
            {
                "id": p.id,
                "amount": float(p.amount),
                "currency": p.currency,
                "status": p.status,
                "description": p.description,
                "refunded_amount": float(p.refunded_amount or 0),
                "created_at": serializers.iso(p.created_at),
            }
            for p in rows
        ],
        "refunds": [
            {
                "id": r.id,
                "amount": float(r.amount),
                "currency": r.currency,
                "status": r.status,
                "reason": r.reason,
                "created_at": serializers.iso(r.created_at),
            }
            for r in refunds
        ],
    }


@router.get("/billing/performance-fee")
def performance_fee_state(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.services import performance_fees

    settings_value = performance_fees.settings_for(db)
    consent = performance_fees.consent_for(db, user.org_id)
    return {
        "available": entitlements.has_feature(db, user.org_id, entitlements.Entitlement.PERFORMANCE_FEES),
        "enabled": bool(settings_value.get("enabled")),
        "rate": settings_value.get("rate"),
        "currency": settings_value.get("currency"),
        "document_version": performance_fees.DOCUMENT_VERSION,
        "legal_review_completed": bool(settings_value.get("legal_review_completed")),
        "jurisdictions_allowed": settings_value.get("jurisdictions_allowed") or [],
        "consent": (
            {
                "id": consent.id,
                "fee_rate": float(consent.fee_rate),
                "accepted_at": serializers.iso(consent.accepted_at),
                "document_version": consent.document_version,
            }
            if consent
            else None
        ),
        "note": (
            "Performance fees are opt-in, charged only on realised net P&L above a high-water mark, and are not "
            "offered until legal review is complete."
        ),
    }


@router.post("/billing/performance-fee/consent", status_code=201)
def accept_performance_fee(
    payload: ConsentRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.services import performance_fees

    settings_value = performance_fees.settings_for(db)
    consent = performance_fees.record_consent(
        db,
        user=user,
        accepted=payload.accepted,
        fee_rate=float(settings_value.get("rate") or 0.0),
        ip=request.client.host if request.client else None,
        snapshot={"accepted_from": "billing_page"},
    )
    db.commit()
    return {"status": "accepted", "consent_id": consent.id, "fee_rate": float(consent.fee_rate)}


@router.post("/webhooks/billing/{provider}", include_in_schema=True)
async def billing_webhook(provider: str, request: Request, db: Session = Depends(get_db)):
    """Signature-verified provider callback. The only path that can change entitlements."""
    raw = await request.body()
    headers = {k: v for k, v in request.headers.items()}
    result = billing.process_webhook(db, provider=provider, raw_body=raw, headers=headers)
    db.commit()
    return result
