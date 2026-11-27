"""Branded transactional email templates.

Every message shares one layout: a midnight header, a white content card, and a charcoal
footer carrying the reason the message was sent plus the unsubscribe route. Content is
plain HTML built from escaped values only — no template engine, so nothing a user types
can inject markup.

The palette matches the product: midnight navy, charcoal, champagne accent, and the
red/green pair used for risk and profit figures.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field

from app.core.config import settings

MIDNIGHT = "#0b1220"
CHARCOAL = "#151b26"
CARD = "#ffffff"
INK = "#111827"
MUTED = "#5b6472"
BORDER = "#e5e7eb"
GOLD = "#c8a96a"
RED = "#b42318"
GREEN = "#067647"
FONT = (
    "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
)


@dataclass(frozen=True)
class RenderedEmail:
    subject: str
    html: str
    text: str
    template: str
    category: str = "system"
    # Promotional mail carries an unsubscribe link; transactional mail does not, because
    # suppressing it would hide security and billing notices.
    promotional: bool = False
    meta: dict = field(default_factory=dict)


def _escape(value: str) -> str:
    return html.escape(value or "", quote=True)


def layout(
    *,
    title: str,
    body_html: str,
    preheader: str = "",
    footer_reason: str = "You are receiving this because you have a VELTRANE account.",
    unsubscribe_url: str = "",
) -> str:
    unsubscribe = (
        f'<p style="margin:12px 0 0"><a href="{_escape(unsubscribe_url)}" '
        f'style="color:#9aa4b2;text-decoration:underline">Unsubscribe from product announcements</a></p>'
        if unsubscribe_url
        else ""
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_escape(title)}</title>
</head>
<body style="margin:0;padding:0;background:#f4f5f7;font-family:{FONT};color:{INK}">
<div style="display:none;max-height:0;overflow:hidden;opacity:0">{_escape(preheader)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f5f7;padding:24px 12px">
  <tr><td align="center">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px">
      <tr>
        <td style="background:{MIDNIGHT};padding:24px 28px;border-radius:12px 12px 0 0">
          <div style="font-family:{FONT};font-size:20px;letter-spacing:6px;color:#f8fafc;font-weight:600">VELTRANE</div>
          <div style="font-size:11px;letter-spacing:2px;color:{GOLD};text-transform:uppercase;margin-top:6px">Autonomous trading, under your control</div>
        </td>
      </tr>
      <tr>
        <td style="background:{CARD};padding:32px 28px;border-left:1px solid {BORDER};border-right:1px solid {BORDER}">
          <h1 style="margin:0 0 16px;font-size:22px;line-height:1.3;color:{INK};font-weight:600">{_escape(title)}</h1>
          <div style="font-size:15px;line-height:1.65;color:{INK}">{body_html}</div>
        </td>
      </tr>
      <tr>
        <td style="background:{CHARCOAL};padding:22px 28px;border-radius:0 0 12px 12px">
          <p style="margin:0;font-size:12px;line-height:1.6;color:#9aa4b2">{_escape(footer_reason)}</p>
          <p style="margin:8px 0 0;font-size:12px;line-height:1.6;color:#9aa4b2">
            VELTRANE never holds your funds and never asks for withdrawal permission on a broker or
            exchange account. Trading involves substantial risk of loss; simulated results are not
            real results.
          </p>
          <p style="margin:8px 0 0;font-size:12px;line-height:1.6;color:#9aa4b2">
            Need help? Reply to this message or write to {_escape(settings.email_reply_to)}.
          </p>
          {unsubscribe}
        </td>
      </tr>
    </table>
  </td></tr>
</table>
</body>
</html>"""


def _button(label: str, url: str, *, tone: str = MIDNIGHT) -> str:
    return (
        f'<p style="margin:24px 0"><a href="{_escape(url)}" '
        f'style="background:{tone};color:#ffffff;text-decoration:none;padding:12px 20px;'
        f'border-radius:8px;font-size:14px;font-weight:600;display:inline-block">{_escape(label)}</a></p>'
    )


def _callout(text: str, *, tone: str = GREEN) -> str:
    return (
        f'<div style="border-left:3px solid {tone};background:#fafafa;padding:12px 16px;margin:16px 0;'
        f'font-size:14px;line-height:1.6;color:{INK}">{_escape(text)}</div>'
    )


def _rows(rows: list[tuple[str, str]]) -> str:
    cells = "".join(
        f'<tr><td style="padding:8px 0;color:{MUTED};font-size:13px">{_escape(label)}</td>'
        f'<td style="padding:8px 0;color:{INK};font-size:13px;text-align:right">{_escape(value)}</td></tr>'
        for label, value in rows
    )
    return f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{cells}</table>'


def verification(name: str, verify_url: str) -> RenderedEmail:
    body = (
        f"<p>Hello {_escape(name or 'there')},</p>"
        "<p>Confirm your email address to finish setting up your VELTRANE account.</p>"
        f"{_button('Verify my email', verify_url)}"
        f"{_callout('The link expires in 24 hours. If you did not create an account, ignore this email.')}"
    )
    return RenderedEmail(
        subject="Verify your VELTRANE email",
        html=layout(
            title="Verify your email",
            body_html=body,
            preheader="One click to activate your VELTRANE account.",
            footer_reason="You are receiving this because an account was created with this address.",
        ),
        text=(
            f"Hello {name or 'there'},\n\nConfirm your email address: {verify_url}\n\n"
            "The link expires in 24 hours. If you did not create an account, ignore this email."
        ),
        template="verification",
        category="security",
    )


def welcome(name: str, dashboard_url: str) -> RenderedEmail:
    body = (
        f"<p>Welcome, {_escape(name or 'trader')}.</p>"
        "<p>Your account is ready. Two things are worth doing before you trade:</p>"
        "<ol style='padding-left:18px;margin:12px 0'>"
        "<li style='margin-bottom:8px'>Connect Deriv in read-only mode and check that your balances sync.</li>"
        "<li>Run a paper strategy so you can see costs, slippage and the risk checks on every order.</li>"
        "</ol>"
        f"{_button('Open VELTRANE', dashboard_url)}"
        f"{_callout('Live trading stays off until you authorise it explicitly. Paper trading never touches real money.')}"
    )
    return RenderedEmail(
        subject="Welcome to VELTRANE",
        html=layout(
            title="Welcome to VELTRANE",
            body_html=body,
            preheader="Connect an account, then start with paper trading.",
        ),
        text=(
            f"Welcome, {name or 'trader'}.\n\n"
            f"Open VELTRANE: {dashboard_url}\n\n"
            "Connect Deriv in read-only mode, then run a paper strategy. Live trading stays off "
            "until you authorise it explicitly."
        ),
        template="welcome",
        category="system",
    )


def password_reset(name: str, reset_url: str) -> RenderedEmail:
    body = (
        f"<p>Hello {_escape(name or 'there')},</p>"
        "<p>We received a request to reset your VELTRANE password.</p>"
        f"{_button('Choose a new password', reset_url)}"
        f"{_callout('The link expires in 60 minutes. If you did not request this, no action is needed and your password is unchanged.', tone=RED)}"
    )
    return RenderedEmail(
        subject="Reset your VELTRANE password",
        html=layout(
            title="Reset your password",
            body_html=body,
            preheader="A password reset was requested for your account.",
            footer_reason="You are receiving this because a password reset was requested for your account.",
        ),
        text=(
            f"Hello {name or 'there'},\n\nReset your password: {reset_url}\n\n"
            "The link expires in 60 minutes. If you did not request this, ignore this email."
        ),
        template="password_reset",
        category="security",
    )


def security_alert(name: str, event: str, when: str, action_url: str) -> RenderedEmail:
    body = (
        f"<p>Hello {_escape(name or 'there')},</p>"
        f"<p>{_escape(event)}</p>"
        f"{_rows([('When', when)])}"
        f"{_button('Review account security', action_url)}"
        f"{_callout('If this was not you, change your password and revoke sessions immediately.', tone=RED)}"
    )
    return RenderedEmail(
        subject="VELTRANE security notice",
        html=layout(
            title="Security notice",
            body_html=body,
            preheader=event,
            footer_reason="You are receiving this because of a security event on your account.",
        ),
        text=f"Hello {name or 'there'},\n\n{event}\nWhen: {when}\n\nReview: {action_url}",
        template="security_alert",
        category="security",
    )


def deriv_connected(name: str, accounts: list[dict], dashboard_url: str) -> RenderedEmail:
    demo = sum(1 for a in accounts if str(a.get("account_type", "")).lower() == "demo")
    real = len(accounts) - demo
    body = (
        f"<p>Hello {_escape(name or 'there')},</p>"
        "<p>Your Deriv account is connected to VELTRANE.</p>"
        f"{_rows([('Accounts available', str(len(accounts))), ('Demo accounts', str(demo)), ('Real accounts', str(real))])}"
        f"{_button('Review connected accounts', dashboard_url)}"
        f"{_callout('Access is read-only until you enable trading permissions. VELTRANE never requests withdrawal access.')}"
    )
    return RenderedEmail(
        subject="Deriv connected to VELTRANE",
        html=layout(
            title="Deriv connected",
            body_html=body,
            preheader="Your Deriv accounts are now visible in VELTRANE.",
            footer_reason="You are receiving this because you connected a broker account.",
        ),
        text=(
            f"Hello {name or 'there'},\n\nDeriv is connected: {len(accounts)} account(s) "
            f"({demo} demo, {real} real).\n\nReview: {dashboard_url}"
        ),
        template="deriv_connected",
        category="deriv",
    )


def subscription_changed(name: str, plan: str, status: str, amount: str, billing_url: str) -> RenderedEmail:
    body = (
        f"<p>Hello {_escape(name or 'there')},</p>"
        f"<p>Your subscription is now <strong>{_escape(plan)}</strong>.</p>"
        f"{_rows([('Status', status), ('Amount', amount)])}"
        f"{_button('Manage billing', billing_url)}"
    )
    return RenderedEmail(
        subject=f"Your VELTRANE plan: {plan}",
        html=layout(
            title="Subscription update",
            body_html=body,
            preheader=f"Your plan is now {plan}.",
            footer_reason="You are receiving this because you have a VELTRANE subscription.",
        ),
        text=f"Hello {name or 'there'},\n\nPlan: {plan}\nStatus: {status}\nAmount: {amount}\n\nBilling: {billing_url}",
        template="subscription_changed",
        category="billing",
    )


def payment_failed(name: str, amount: str, retry_url: str) -> RenderedEmail:
    body = (
        f"<p>Hello {_escape(name or 'there')},</p>"
        f"<p>A payment of {_escape(amount)} did not go through. Access continues while the processor retries.</p>"
        f"{_button('Update payment method', retry_url, tone=RED)}"
        f"{_callout('If the retry fails, the subscription returns to Free. No trading positions are closed by a billing event.', tone=RED)}"
    )
    return RenderedEmail(
        subject="Action needed: payment failed",
        html=layout(
            title="Payment failed",
            body_html=body,
            preheader="Update your payment method to keep your plan.",
            footer_reason="You are receiving this because a subscription payment failed.",
        ),
        text=f"Hello {name or 'there'},\n\nA payment of {amount} failed.\n\nUpdate: {retry_url}",
        template="payment_failed",
        category="billing",
    )


def risk_alert(name: str, title: str, detail: str, risk_url: str, *, severity: str = "warning") -> RenderedEmail:
    tone = RED if severity in {"critical", "error"} else GOLD
    body = (
        f"<p>Hello {_escape(name or 'there')},</p>"
        f"<p><strong>{_escape(title)}</strong></p>"
        f"{_callout(detail, tone=tone)}"
        f"{_button('Open risk controls', risk_url)}"
    )
    return RenderedEmail(
        subject=f"VELTRANE risk notice: {title}",
        html=layout(
            title="Risk notice",
            body_html=body,
            preheader=title,
            footer_reason="You are receiving this because a risk limit or trading control changed on your account.",
        ),
        text=f"Hello {name or 'there'},\n\n{title}\n\n{detail}\n\n{risk_url}",
        template="risk_alert",
        category="risk",
    )


def trading_digest(
    name: str,
    *,
    period: str,
    opened: int,
    closed: int,
    rejected: int,
    realised: str,
    positions: int,
    detail_url: str,
    note: str = "",
) -> RenderedEmail:
    tone = GREEN if not realised.strip().startswith("-") else RED
    body = (
        f"<p>Hello {_escape(name or 'there')},</p>"
        f"<p>Here is your trading activity for {_escape(period)}.</p>"
        f"{_rows([('Positions opened', str(opened)), ('Positions closed', str(closed)), ('Orders rejected by risk', str(rejected)), ('Open positions', str(positions)), ('Realised P&L after costs', realised)])}"
        f'<p style="margin:12px 0;font-size:13px;color:{tone}">{_escape(note)}</p>'
        f"{_button('See the full activity log', detail_url)}"
        f"{_callout('One digest a day instead of an email per trade. Trade-level alerts stay in the app.')}"
    )
    return RenderedEmail(
        subject=f"VELTRANE daily digest — {period}",
        html=layout(
            title="Daily trading digest",
            body_html=body,
            preheader=f"{opened} opened, {closed} closed, realised {realised}.",
            footer_reason="You are receiving the daily digest because it is enabled in your notification settings.",
        ),
        text=(
            f"Hello {name or 'there'},\n\nTrading activity for {period}\n"
            f"Opened: {opened}\nClosed: {closed}\nRejected by risk: {rejected}\n"
            f"Open positions: {positions}\nRealised P&L after costs: {realised}\n\n{note}\n\n{detail_url}"
        ),
        template="trading_digest",
        category="digest",
    )


def announcement(title: str, body_text: str, cta_label: str, cta_url: str, unsubscribe_url: str) -> RenderedEmail:
    paragraphs = "".join(f"<p>{_escape(line)}</p>" for line in body_text.split("\n") if line.strip())
    body = f"{paragraphs}{_button(cta_label or 'Open VELTRANE', cta_url) if cta_url else ''}"
    return RenderedEmail(
        subject=title,
        html=layout(
            title=title,
            body_html=body,
            preheader=body_text.strip().split("\n")[0][:140] if body_text.strip() else title,
            footer_reason="You are receiving this because you have a VELTRANE account.",
            unsubscribe_url=unsubscribe_url,
        ),
        text=f"{title}\n\n{body_text}\n\n{cta_url}\n\nUnsubscribe: {unsubscribe_url}",
        template="announcement",
        category="announcement",
        promotional=True,
    )


def generic_notice(
    title: str,
    body_text: str,
    action_url: str,
    *,
    severity: str = "info",
    category: str = "system",
) -> RenderedEmail:
    """Fallback for notifications without a dedicated template."""
    tone = RED if severity in {"critical", "error"} else (GOLD if severity == "warning" else GREEN)
    paragraphs = "".join(f"<p>{_escape(line)}</p>" for line in body_text.split("\n") if line.strip())
    body = (
        f"{paragraphs or f'<p>{_escape(title)}</p>'}"
        f"{_button('Open VELTRANE', action_url) if action_url else ''}"
        f"{_callout('This message reflects a confirmed state change. Simulated activity is always labelled as such.', tone=tone)}"
    )
    return RenderedEmail(
        subject=title,
        html=layout(
            title=title,
            body_html=body,
            preheader=body_text.strip().split("\n")[0][:140] if body_text.strip() else title,
            footer_reason="You are receiving this because of activity on your VELTRANE account.",
        ),
        text=f"{title}\n\n{body_text}\n\n{action_url}",
        template="notice",
        category=category,
    )


#: Templates an administrator can pick in the email centre. Transactional templates are
#: excluded: sending a "password reset" as a campaign would be misleading.
CAMPAIGN_TEMPLATES = {"announcement": "Announcement", "maintenance": "Maintenance notice"}

TEMPLATE_SUBJECTS = {
    "announcement": "A VELTRANE update",
    "maintenance": "Scheduled maintenance window",
}


def render_campaign(template: str, *, title: str, body_text: str, cta_url: str, unsubscribe_url: str) -> RenderedEmail:
    rendered = announcement(title, body_text, "Open VELTRANE", cta_url, unsubscribe_url)
    if template == "maintenance":
        return RenderedEmail(
            subject=title,
            html=rendered.html,
            text=rendered.text,
            template="maintenance",
            category="system",
            promotional=True,
        )
    return rendered
