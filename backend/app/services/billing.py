"""Payment abstraction, webhook verification and subscription state machine.

Design rules enforced here:
* A frontend "payment succeeded" message is never trusted. Entitlements change only
  after a signature-verified provider event is persisted.
* Every webhook is idempotent on (provider, event_id).
* Card data never touches this service; providers hand us tokens/ids only.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
from app.core.config import settings
from app.core.errors import bad_request, conflict, not_found
from app.db.constants import AuditAction, NotificationCategory, PlanCode, Severity, SubscriptionStatus
from app.db.models import Invoice, Payment, Plan, Refund, Subscription, User, WebhookEvent
from app.services import audit, notifications
from app.services.entitlements import PAST_DUE_GRACE_DAYS
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)
MOCK_PROVIDER = "mock"
STRIPE_PROVIDER = "stripe"


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class ProviderEvent:
    provider: str
    event_id: str
    event_type: str
    payload: dict


# --------------------------------------------------------------------------- #
# Signature verification
# --------------------------------------------------------------------------- #
def _mock_secret() -> bytes:
    return hashlib.sha256(f"mock-billing::{settings.secret_key}".encode()).digest()


def sign_mock_payload(body: bytes, timestamp: int | None = None) -> tuple[str, str]:
    ts = str(timestamp or int(time.time()))
    mac = hmac.new(_mock_secret(), ts.encode() + b"." + body, hashlib.sha256).hexdigest()
    return ts, mac


def verify_mock_signature(body: bytes, headers: dict[str, str]) -> bool:
    ts = headers.get("x-mock-timestamp") or headers.get("X-Mock-Timestamp")
    sig = headers.get("x-mock-signature") or headers.get("X-Mock-Signature")
    if not ts or not sig:
        return False
    try:
        if abs(int(time.time()) - int(ts)) > settings.billing_webhook_tolerance_seconds:
            return False
    except ValueError:
        return False
    expected = hmac.new(_mock_secret(), ts.encode() + b"." + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


def verify_stripe_signature(body: bytes, header: str | None) -> bool:
    """Stripe scheme: ``t=<unix>,v1=<hex hmac>`` over ``<t>.<body>``."""
    if not header or not settings.stripe_webhook_secret:
        return False
    parts = dict(item.split("=", 1) for item in header.split(",") if "=" in item)
    timestamp, signature = parts.get("t"), parts.get("v1")
    if not timestamp or not signature:
        return False
    try:
        if abs(int(time.time()) - int(timestamp)) > settings.billing_webhook_tolerance_seconds:
            return False
    except ValueError:
        return False
    expected = hmac.new(
        settings.stripe_webhook_secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


# --------------------------------------------------------------------------- #
# Provider adapters
# --------------------------------------------------------------------------- #
class BillingProvider:
    name = "abstract"

    def create_checkout(self, *, org_id: str, plan: Plan, user: User, subscription: Subscription) -> dict:
        raise NotImplementedError

    def refund(self, payment: Payment, amount: float) -> dict:
        raise NotImplementedError

    def cancel(self, subscription: Subscription) -> dict:
        raise NotImplementedError


class MockBillingProvider(BillingProvider):
    """Local-only simulator. It still goes through signed-webhook verification."""

    name = MOCK_PROVIDER

    def create_checkout(self, *, org_id: str, plan: Plan, user: User, subscription: Subscription) -> dict:
        nonce = secrets.token_urlsafe(24)
        payload = {
            "org_id": org_id,
            "plan_code": plan.code,
            "amount": float(plan.price_monthly),
            "currency": plan.currency,
            "nonce": nonce,
            "exp": int(time.time()) + 1800,
            "email": user.email,
        }
        body = json.dumps(payload, separators=(",", ":")).encode()
        ts, sig = sign_mock_payload(body)
        token = f"{ts}.{sig}.{body.decode()}"
        return {
            "provider": self.name,
            "mode": "mock",
            "checkout_token": token,
            "amount": float(plan.price_monthly),
            "currency": plan.currency,
            "plan_code": plan.code,
            "expires_in": 1800,
        }

    def refund(self, payment: Payment, amount: float) -> dict:
        return {"provider_refund_id": f"re_mock_{secrets.token_hex(8)}", "status": "succeeded"}

    def cancel(self, subscription: Subscription) -> dict:
        return {"status": "canceled"}


class StripeBillingProvider(BillingProvider):
    """Thin Stripe REST adapter (no SDK) — create checkout sessions and refunds."""

    name = STRIPE_PROVIDER
    api = "https://api.stripe.com/v1"

    def _post(self, path: str, data: dict) -> dict:
        if not settings.stripe_secret_key:
            raise bad_request("stripe_not_configured", "Stripe is not configured for this deployment.")
        with httpx.Client(timeout=20) as client:
            resp = client.post(
                f"{self.api}{path}",
                data=data,
                auth=(settings.stripe_secret_key, ""),
                headers={"Idempotency-Key": data.pop("_idempotency_key", secrets.token_hex(16))},
            )
        if resp.status_code >= 400:
            log.error("stripe_error", extra={"extra_fields": {"status": resp.status_code, "body": resp.text[:500]}})
            raise bad_request("payment_provider_error", "The payment provider rejected the request.")
        return resp.json()

    def create_checkout(self, *, org_id: str, plan: Plan, user: User, subscription: Subscription) -> dict:
        session = self._post(
            "/checkout/sessions",
            {
                "mode": "subscription",
                "customer_email": user.email,
                "success_url": f"{settings.web_base_url}/billing?checkout=success&session_id={{CHECKOUT_SESSION_ID}}",
                "cancel_url": f"{settings.web_base_url}/billing?checkout=cancelled",
                "line_items[0][price_data][currency]": plan.currency.lower(),
                "line_items[0][price_data][unit_amount]": str(int(round(float(plan.price_monthly) * 100))),
                "line_items[0][price_data][recurring][interval]": "month",
                "line_items[0][price_data][product_data][name]": f"VELTRANE {plan.name}",
                "line_items[0][quantity]": "1",
                "metadata[org_id]": org_id,
                "metadata[plan_code]": plan.code,
                "subscription_data[metadata][org_id]": org_id,
                "subscription_data[metadata][plan_code]": plan.code,
                "_idempotency_key": f"checkout:{org_id}:{plan.code}:{int(time.time()) // 60}",
            },
        )
        return {
            "provider": self.name,
            "mode": "live",
            "checkout_url": session.get("url"),
            "session_id": session.get("id"),
            "amount": float(plan.price_monthly),
            "currency": plan.currency,
            "plan_code": plan.code,
        }

    def refund(self, payment: Payment, amount: float) -> dict:
        result = self._post(
            "/refunds",
            {
                "payment_intent": payment.provider_payment_id,
                "amount": str(int(round(amount * 100))),
                "_idempotency_key": f"refund:{payment.id}:{int(round(amount * 100))}",
            },
        )
        return {"provider_refund_id": result.get("id"), "status": result.get("status", "pending")}

    def cancel(self, subscription: Subscription) -> dict:
        if not subscription.provider_subscription_id:
            return {"status": "noop"}
        with httpx.Client(timeout=20) as client:
            resp = client.post(
                f"{self.api}/subscriptions/{subscription.provider_subscription_id}",
                data={"cancel_at_period_end": "true"},
                auth=(settings.stripe_secret_key, ""),
            )
        return {"status": "scheduled" if resp.status_code < 400 else "error"}


def provider_for(name: str | None = None) -> BillingProvider:
    name = name or settings.billing_provider
    if name == STRIPE_PROVIDER:
        return StripeBillingProvider()
    if name == MOCK_PROVIDER:
        return MockBillingProvider()
    raise bad_request("unknown_billing_provider", "Unsupported billing provider.")


# --------------------------------------------------------------------------- #
# Subscription lifecycle
# --------------------------------------------------------------------------- #
def ensure_free_subscription(db: Session, org_id: str) -> Subscription:
    sub = db.query(Subscription).filter(Subscription.org_id == org_id).order_by(Subscription.created_at.desc()).first()
    if sub:
        return sub
    now = utcnow()
    sub = Subscription(
        org_id=org_id,
        plan_code=PlanCode.FREE,
        status=SubscriptionStatus.ACTIVE,
        provider=MOCK_PROVIDER,
        current_period_start=now,
        current_period_end=now + timedelta(days=365 * 50),
    )
    db.add(sub)
    db.flush()
    return sub


def _next_invoice_number(db: Session) -> str:
    stamp = utcnow().strftime("%Y%m")
    count = db.query(Invoice).filter(Invoice.number.like(f"INV-{stamp}-%")).count() + 1
    return f"INV-{stamp}-{count:05d}"


def create_checkout(db: Session, *, org: str, plan_code: str, user: User) -> dict:
    plan = db.get(Plan, plan_code)
    if plan is None or not plan.is_active:
        raise not_found("plan_not_found", "That plan is not available.")
    if plan.code == PlanCode.FREE:
        raise bad_request("free_plan_no_checkout", "The Free plan does not require payment.")
    sub = ensure_free_subscription(db, org)
    provider = provider_for()
    checkout = provider.create_checkout(org_id=org, plan=plan, user=user, subscription=sub)
    audit.record(
        db,
        action=AuditAction.SUBSCRIPTION_CHANGED,
        org_id=org,
        actor_user_id=user.id,
        actor_email=user.email,
        target_type="plan",
        target_id=plan.code,
        meta={"stage": "checkout_created", "provider": provider.name, "amount": float(plan.price_monthly)},
    )
    return checkout


def complete_mock_checkout(db: Session, token: str) -> dict:
    """Simulate the provider's server-to-server confirmation for local development.

    The resulting event travels through the exact same verified webhook path as a
    real provider, so the activation code is the code that runs in production.
    """
    if settings.is_production:
        raise bad_request("mock_disabled", "Mock checkout is disabled in production.")
    try:
        ts_str, sig, body = token.split(".", 2)
        ts = int(ts_str)
    except (ValueError, AttributeError):
        raise bad_request("invalid_checkout_token", "Malformed checkout token.") from None
    if abs(int(time.time()) - ts) > 1800:
        raise bad_request("checkout_expired", "This checkout session has expired.")
    expected = hmac.new(_mock_secret(), ts_str.encode() + b"." + body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        raise bad_request("invalid_checkout_token", "Checkout token signature is invalid.")
    payload = json.loads(body)
    event = {
        "id": f"evt_mock_{secrets.token_hex(10)}",
        "type": "checkout.session.completed",
        "created": int(time.time()),
        "data": {
            "object": {
                "id": f"cs_mock_{secrets.token_hex(8)}",
                "amount_total": int(round(payload["amount"] * 100)),
                "currency": payload["currency"].lower(),
                "metadata": {"org_id": payload["org_id"], "plan_code": payload["plan_code"]},
                "customer_email": payload["email"],
                "subscription": f"sub_mock_{secrets.token_hex(8)}",
            }
        },
    }
    raw = json.dumps(event).encode()
    ts_h, sig_h = sign_mock_payload(raw)
    return process_webhook(
        db,
        provider=MOCK_PROVIDER,
        raw_body=raw,
        headers={"x-mock-timestamp": ts_h, "x-mock-signature": sig_h},
    )


def activate_plan(
    db: Session,
    *,
    org_id: str,
    plan_code: str,
    provider: str,
    provider_subscription_id: str | None,
    amount: float,
    currency: str = "USD",
    event_id: str,
    trial: bool = True,
) -> Subscription:
    plan = db.get(Plan, plan_code)
    if plan is None:
        raise not_found("plan_not_found", "Unknown plan on webhook payload.")
    sub = ensure_free_subscription(db, org_id)
    now = utcnow()
    period_end = now + timedelta(days=30)
    sub.plan_code = plan_code
    sub.provider = provider
    sub.provider_subscription_id = provider_subscription_id
    # A collected payment means the paid period has started; a trial only applies
    # when nothing was charged for this period.
    trial_applies = bool(trial and plan.trial_days and amount <= 0)
    sub.status = SubscriptionStatus.TRIALING if trial_applies else SubscriptionStatus.ACTIVE
    sub.current_period_start = now
    sub.current_period_end = period_end
    sub.trial_end = now + timedelta(days=plan.trial_days) if trial_applies else None
    sub.cancel_at_period_end = False
    sub.canceled_at = None
    sub.pending_plan_code = None
    sub.pending_effective_at = None
    db.flush()

    if amount > 0:
        payment = Payment(
            org_id=org_id,
            provider=provider,
            provider_payment_id=f"pi_{event_id}",
            amount=amount,
            currency=currency,
            status="succeeded",
            idempotency_key=f"activate:{org_id}:{plan_code}:{event_id}",
            description=f"{plan.name} plan — first period",
        )
        db.add(payment)
        invoice = Invoice(
            org_id=org_id,
            number=_next_invoice_number(db),
            subtotal=amount,
            tax=0,
            total=amount,
            currency=currency,
            status="paid",
            period_start=now,
            period_end=period_end,
            paid_at=now,
            line_items=[{"description": f"{plan.name} monthly subscription", "amount": amount}],
        )
        db.add(invoice)
        db.flush()
        audit.record(
            db,
            action=AuditAction.PAYMENT_SUCCEEDED,
            org_id=org_id,
            target_type="payment",
            target_id=payment.id,
            meta={"amount": amount, "currency": currency, "plan": plan_code, "provider": provider},
        )
    notifications.notify(
        db,
        org_id=org_id,
        category=NotificationCategory.BILLING,
        severity=Severity.SUCCESS,
        title=f"Subscription active: {plan.name}",
        body=(
            f"Your {plan.name} plan is active. "
            + ("A 7-day trial applies; the first charge follows the trial. " if sub.status == "trialing" else "")
            + "Live trading still requires explicit authorisation and is disabled by default."
        ),
        data={"plan_code": plan_code, "status": sub.status},
    )
    return sub


def _org_for_event(db: Session, obj: dict) -> str | None:
    meta = obj.get("metadata") or {}
    return meta.get("org_id")


def process_webhook(
    db: Session,
    *,
    provider: str,
    raw_body: bytes,
    headers: dict[str, str],
) -> dict:
    """Verify, persist and apply a provider webhook exactly once."""
    normalized = {k.lower(): v for k, v in headers.items()}
    if provider == STRIPE_PROVIDER:
        valid = verify_stripe_signature(raw_body, normalized.get("stripe-signature"))
    elif provider == MOCK_PROVIDER:
        valid = verify_mock_signature(raw_body, normalized)
    else:
        raise bad_request("unknown_billing_provider", "Unsupported billing provider.")

    if not valid:
        audit.record(
            db,
            action="billing.webhook_rejected",
            meta={"provider": provider, "reason": "invalid_signature"},
        )
        db.commit()
        raise bad_request("invalid_signature", "Webhook signature verification failed.")

    try:
        event = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise bad_request("invalid_payload", "Webhook payload is not valid JSON.") from exc

    event_id = str(event.get("id") or "")
    event_type = str(event.get("type") or "")
    if not event_id or not event_type:
        raise bad_request("invalid_payload", "Webhook payload is missing id/type.")

    existing = (
        db.query(WebhookEvent)
        .filter(WebhookEvent.provider == provider, WebhookEvent.event_id == event_id)
        .first()
    )
    if existing and existing.status == "processed":
        return {"status": "already_processed", "event_id": event_id}

    record = existing or WebhookEvent(provider=provider, event_id=event_id, event_type=event_type)
    record.payload = event
    record.signature_valid = True
    record.status = "processing"
    if existing is None:
        db.add(record)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return {"status": "already_processed", "event_id": event_id}

    obj = (event.get("data") or {}).get("object") or {}
    org_id = _org_for_event(db, obj)
    try:
        result = _apply_event(db, provider=provider, event_type=event_type, obj=obj, org_id=org_id, event_id=event_id)
        record.status = "processed"
        record.processed_at = utcnow()
        db.flush()
        return {"status": "processed", "event_id": event_id, **result}
    except Exception as exc:  # noqa: BLE001 - persist failure state, surface to caller
        record.status = "failed"
        record.error = str(exc)[:1000]
        db.flush()
        log.exception("webhook_processing_failed")
        raise bad_request("webhook_processing_failed", "The webhook could not be applied.") from exc


def _apply_event(
    db: Session, *, provider: str, event_type: str, obj: dict, org_id: str | None, event_id: str
) -> dict:
    if event_type == "checkout.session.completed":
        if not org_id:
            raise bad_request("missing_org", "Checkout session is missing org metadata.")
        plan_code = (obj.get("metadata") or {}).get("plan_code")
        amount = float(obj.get("amount_total", 0)) / 100.0
        currency = str(obj.get("currency", "usd")).upper()
        sub = activate_plan(
            db,
            org_id=org_id,
            plan_code=plan_code,
            provider=provider,
            provider_subscription_id=obj.get("subscription"),
            amount=amount,
            currency=currency,
            event_id=event_id,
        )
        return {"subscription": sub.id, "plan_code": sub.plan_code}

    if event_type in ("invoice.payment_succeeded", "invoice.paid"):
        if not org_id:
            return {"ignored": "missing_org"}
        sub = (
            db.query(Subscription)
            .filter(Subscription.org_id == org_id)
            .order_by(Subscription.created_at.desc())
            .first()
        )
        if sub is None:
            return {"ignored": "no_subscription"}
        now = utcnow()
        sub.status = SubscriptionStatus.ACTIVE
        sub.current_period_start = now
        sub.current_period_end = now + timedelta(days=30)
        if sub.pending_plan_code and (sub.pending_effective_at is None or sub.pending_effective_at <= now):
            sub.plan_code = sub.pending_plan_code
            sub.pending_plan_code = None
            sub.pending_effective_at = None
        amount = float(obj.get("amount_paid", 0)) / 100.0
        currency = str(obj.get("currency", "usd")).upper()
        if amount > 0:
            db.add(
                Payment(
                    org_id=org_id,
                    provider=provider,
                    provider_payment_id=str(obj.get("payment_intent") or f"pi_{event_id}"),
                    provider_invoice_id=str(obj.get("id") or ""),
                    amount=amount,
                    currency=currency,
                    status="succeeded",
                    idempotency_key=f"invoice:{event_id}",
                    description="Subscription renewal",
                )
            )
            db.add(
                Invoice(
                    org_id=org_id,
                    number=_next_invoice_number(db),
                    subtotal=amount,
                    total=amount,
                    currency=currency,
                    status="paid",
                    period_start=now,
                    period_end=sub.current_period_end,
                    paid_at=now,
                    provider_invoice_id=str(obj.get("id") or ""),
                    line_items=[{"description": "Monthly subscription renewal", "amount": amount}],
                )
            )
        db.flush()
        audit.record(
            db,
            action=AuditAction.PAYMENT_SUCCEEDED,
            org_id=org_id,
            target_type="subscription",
            target_id=sub.id,
            meta={"amount": amount, "currency": currency, "kind": "renewal"},
        )
        return {"subscription": sub.id, "status": sub.status}

    if event_type in ("invoice.payment_failed",):
        if not org_id:
            return {"ignored": "missing_org"}
        sub = (
            db.query(Subscription)
            .filter(Subscription.org_id == org_id)
            .order_by(Subscription.created_at.desc())
            .first()
        )
        if sub:
            sub.status = SubscriptionStatus.PAST_DUE
            db.flush()
            notifications.notify(
                db,
                org_id=org_id,
                category=NotificationCategory.BILLING,
                severity=Severity.CRITICAL,
                title="Payment failed — update your payment method",
                body=(
                    "We could not collect your subscription payment. Access continues for "
                    f"{PAST_DUE_GRACE_DAYS} days, then reverts to the Free plan. No live orders can be placed "
                    "while a subscription is past due."
                ),
            )
            audit.record(
                db,
                action=AuditAction.PAYMENT_FAILED,
                org_id=org_id,
                target_type="subscription",
                target_id=sub.id,
            )
        return {"status": "past_due"}

    if event_type in ("customer.subscription.deleted", "customer.subscription.canceled"):
        if not org_id:
            return {"ignored": "missing_org"}
        sub = (
            db.query(Subscription)
            .filter(Subscription.org_id == org_id)
            .order_by(Subscription.created_at.desc())
            .first()
        )
        if sub:
            sub.status = SubscriptionStatus.CANCELED
            sub.canceled_at = utcnow()
            sub.plan_code = PlanCode.FREE
            sub.cancel_at_period_end = False
            db.flush()
            notifications.notify(
                db,
                org_id=org_id,
                category=NotificationCategory.BILLING,
                severity=Severity.WARNING,
                title="Subscription cancelled",
                body="Your paid plan has ended and the account is now on the Free plan.",
            )
            audit.record(
                db,
                action=AuditAction.SUBSCRIPTION_CHANGED,
                org_id=org_id,
                target_type="subscription",
                target_id=sub.id,
                meta={"status": "canceled"},
            )
        return {"status": "canceled"}

    if event_type in ("charge.refunded", "refund.created"):
        if not org_id:
            return {"ignored": "missing_org"}
        amount = float(obj.get("amount_refunded", obj.get("amount", 0))) / 100.0
        db.add(
            Refund(
                org_id=org_id,
                payment_id=None,  # provider-side refund without a local payment link
                amount=amount,
                currency=str(obj.get("currency", "usd")).upper(),
                status="succeeded",
                reason="Provider-initiated refund",
                provider_refund_id=str(obj.get("id") or ""),
            )
        )
        db.flush()
        audit.record(db, action=AuditAction.REFUND_ISSUED, org_id=org_id, meta={"amount": amount})
        return {"refund": amount}

    return {"ignored": event_type}


# --------------------------------------------------------------------------- #
# User-facing operations
# --------------------------------------------------------------------------- #
def cancel_subscription(db: Session, *, org_id: str, user: User, immediate: bool = False) -> Subscription:
    sub = (
        db.query(Subscription)
        .filter(Subscription.org_id == org_id)
        .order_by(Subscription.created_at.desc())
        .first()
    )
    if sub is None:
        raise not_found("subscription_not_found", "No subscription found.")
    if sub.plan_code == PlanCode.FREE:
        raise bad_request("free_plan", "The Free plan cannot be cancelled.")
    provider = provider_for(sub.provider)
    provider.cancel(sub)
    if immediate:
        sub.status = SubscriptionStatus.CANCELED
        sub.plan_code = PlanCode.FREE
        sub.canceled_at = utcnow()
        sub.cancel_at_period_end = False
    else:
        sub.cancel_at_period_end = True
    db.flush()
    audit.record(
        db,
        action=AuditAction.SUBSCRIPTION_CHANGED,
        org_id=org_id,
        actor_user_id=user.id,
        actor_email=user.email,
        target_type="subscription",
        target_id=sub.id,
        meta={"action": "cancel", "immediate": immediate},
    )
    notifications.notify(
        db,
        org_id=org_id,
        category=NotificationCategory.BILLING,
        severity=Severity.WARNING,
        title="Cancellation scheduled" if not immediate else "Subscription cancelled",
        body=(
            "Your plan stays active until the end of the current billing period."
            if not immediate
            else "Your account has moved to the Free plan."
        ),
    )
    return sub


def change_plan(db: Session, *, org_id: str, user: User, new_plan_code: str) -> dict:
    plan = db.get(Plan, new_plan_code)
    if plan is None or not plan.is_active:
        raise not_found("plan_not_found", "That plan is not available.")
    sub = (
        db.query(Subscription)
        .filter(Subscription.org_id == org_id)
        .order_by(Subscription.created_at.desc())
        .first()
    )
    if sub is None:
        sub = ensure_free_subscription(db, org_id)
    if sub.plan_code == new_plan_code:
        raise conflict("same_plan", "You are already on this plan.")
    if new_plan_code == PlanCode.FREE:
        return {"mode": "downgrade", "subscription": cancel_subscription(db, org_id=org_id, user=user).id}
    if sub.plan_code == PlanCode.FREE:
        return {"mode": "checkout", **create_checkout(db, org=org_id, plan_code=new_plan_code, user=user)}
    # Paid -> paid: schedule the change for the next renewal to keep proration simple and honest.
    sub.pending_plan_code = new_plan_code
    sub.pending_effective_at = sub.current_period_end or utcnow()
    db.flush()
    audit.record(
        db,
        action=AuditAction.SUBSCRIPTION_CHANGED,
        org_id=org_id,
        actor_user_id=user.id,
        actor_email=user.email,
        target_type="subscription",
        target_id=sub.id,
        meta={"action": "scheduled_plan_change", "to": new_plan_code},
    )
    notifications.notify(
        db,
        org_id=org_id,
        category=NotificationCategory.BILLING,
        severity=Severity.INFO,
        title=f"Plan change scheduled: {plan.name}",
        body="The new plan takes effect at your next renewal. No charge is made now.",
    )
    return {"mode": "scheduled", "effective_at": sub.pending_effective_at, "plan_code": new_plan_code}


def issue_refund(
    db: Session, *, payment_id: str, amount: float, reason: str, actor: User, org_id: str | None = None
) -> Refund:
    payment = db.get(Payment, payment_id)
    if payment is None:
        raise not_found("payment_not_found", "Payment not found.")
    if org_id and payment.org_id != org_id:
        raise not_found("payment_not_found", "Payment not found.")
    refundable = float(payment.amount) - float(payment.refunded_amount or 0)
    if amount <= 0 or amount > refundable + 1e-9:
        raise bad_request("invalid_refund_amount", f"Refundable amount is {refundable:.2f} {payment.currency}.")
    provider = provider_for(payment.provider)
    result = provider.refund(payment, amount)
    refund = Refund(
        org_id=payment.org_id,
        payment_id=payment.id,
        amount=amount,
        currency=payment.currency,
        status=result.get("status", "pending"),
        reason=reason[:400],
        provider_refund_id=result.get("provider_refund_id"),
        created_by=actor.id,
    )
    db.add(refund)
    payment.refunded_amount = float(payment.refunded_amount or 0) + amount
    payment.status = "refunded" if payment.refunded_amount >= float(payment.amount) else "partially_refunded"
    db.flush()
    audit.record(
        db,
        action=AuditAction.REFUND_ISSUED,
        org_id=payment.org_id,
        actor_user_id=actor.id,
        actor_email=actor.email,
        actor_role=actor.staff_role,
        target_type="payment",
        target_id=payment.id,
        meta={"amount": amount, "reason": reason},
    )
    notifications.notify(
        db,
        org_id=payment.org_id,
        category=NotificationCategory.BILLING,
        severity=Severity.INFO,
        title="Refund issued",
        body=f"A refund of {amount:.2f} {payment.currency} has been issued. Banks may take 5-10 business days.",
    )
    return refund
