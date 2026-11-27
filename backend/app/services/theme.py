"""Runtime visual identity.

The palette lives in ``system_settings`` under one key, so an administrator can change the
platform's colours and the change reaches every open page on its next theme fetch without a
new deployment. Two rules keep this safe:

* Only *colours* are stored, as six-digit hex, and only known tokens are accepted. Nothing
  here can inject CSS, a URL or a script into a page.
* A missing or invalid row falls back to the shipped palette, so a bad save can never leave
  the platform unstyled.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from app.core.errors import bad_request
from app.db.constants import AuditAction
from app.db.models import SystemSetting, User
from app.services import audit
from sqlalchemy.orm import Session

SETTING_KEY = "ui.theme"
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")

# token -> (label, group, default). The order is the order the admin form renders.
PALETTE: dict[str, tuple[str, str, str]] = {
    "background": ("App background", "Surfaces", "#04060a"),
    "surface": ("Panel surface", "Surfaces", "#0a0e15"),
    "surface_raised": ("Raised surface", "Surfaces", "#121821"),
    "border": ("Borders", "Surfaces", "#1b2430"),
    "text": ("Primary text", "Typography", "#e8edf4"),
    "text_muted": ("Secondary text", "Typography", "#98a6b8"),
    "primary": ("Primary action", "Brand", "#2e7bff"),
    "primary_hover": ("Primary hover", "Brand", "#1b5fe0"),
    "secondary": ("Secondary accent", "Brand", "#5c9bff"),
    "accent": ("Accent / highlight", "Brand", "#dcc08a"),
    "button_text": ("Button label", "Brand", "#ffffff"),
    "chart_up": ("Chart up candle", "Charts", "#00e07a"),
    "chart_down": ("Chart down candle", "Charts", "#ff3b52"),
    "chart_grid": ("Chart grid", "Charts", "#141a23"),
    "chart_line": ("Chart overlays", "Charts", "#5c9bff"),
    "gain": ("Profit", "Semantics", "#00e07a"),
    "loss": ("Loss", "Semantics", "#ff3b52"),
    "warn": ("Warning", "Semantics", "#f0b429"),
}

BRANDING_KEYS = ("product_name", "logo_mark", "default_theme", "tagline")

DEFAULT_BRANDING: dict[str, str] = {
    "product_name": "VELTRANE",
    "logo_mark": "V",
    "default_theme": "obsidian",
    "tagline": "Autonomous trading, under your control",
}


def defaults() -> dict[str, Any]:
    return {
        "colors": {token: spec[2] for token, spec in PALETTE.items()},
        "branding": dict(DEFAULT_BRANDING),
        "updated_at": None,
        "updated_by": None,
    }


def _row(db: Session) -> SystemSetting | None:
    return db.get(SystemSetting, SETTING_KEY)


def _clean_colors(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        raise bad_request("invalid_theme", "Colours must be an object of token/hex pairs.")
    unknown = set(raw) - set(PALETTE)
    if unknown:
        raise bad_request("invalid_theme", f"Unknown colour tokens: {', '.join(sorted(unknown))}.")
    colors = {token: spec[2] for token, spec in PALETTE.items()}
    for token, value in raw.items():
        if not isinstance(value, str) or not HEX.match(value):
            raise bad_request("invalid_theme", f"{token} must be a six-digit hex colour such as #1b2430.")
        colors[token] = value.lower()
    return colors


def _clean_branding(raw: Any) -> dict[str, str]:
    branding = dict(DEFAULT_BRANDING)
    if raw is None:
        return branding
    if not isinstance(raw, dict):
        raise bad_request("invalid_branding", "Branding must be an object.")
    unknown = set(raw) - set(BRANDING_KEYS)
    if unknown:
        raise bad_request("invalid_branding", f"Unknown branding keys: {', '.join(sorted(unknown))}.")
    for key, value in raw.items():
        if not isinstance(value, str):
            raise bad_request("invalid_branding", f"{key} must be text.")
        text = value.strip()
        if key == "logo_mark" and len(text) > 3:
            raise bad_request("invalid_branding", "The logo mark is at most three characters.")
        if key == "product_name" and not 2 <= len(text) <= 32:
            raise bad_request("invalid_branding", "The product name must be 2–32 characters.")
        if key == "tagline" and len(text) > 120:
            raise bad_request("invalid_branding", "The tagline is at most 120 characters.")
        if key == "default_theme" and text not in ("obsidian", "light"):
            raise bad_request("invalid_branding", "The default theme must be obsidian or light.")
        branding[key] = text or DEFAULT_BRANDING[key]
    return branding


def get_theme(db: Session) -> dict[str, Any]:
    """Public view: the effective palette plus where it came from."""
    row = _row(db)
    if row is None or not row.value:
        return {**defaults(), "source": "default"}
    stored = row.value
    colors = dict(defaults()["colors"])
    colors.update({k: v for k, v in (stored.get("colors") or {}).items() if k in PALETTE and isinstance(v, str)})
    branding = dict(DEFAULT_BRANDING)
    branding.update({k: v for k, v in (stored.get("branding") or {}).items() if k in BRANDING_KEYS})
    return {
        "colors": colors,
        "branding": branding,
        "updated_at": stored.get("updated_at"),
        "updated_by": stored.get("updated_by"),
        "source": "admin",
    }


def tokens() -> list[dict[str, str]]:
    """Metadata for the admin form: label, group and default for every token."""
    return [
        {"token": token, "label": spec[0], "group": spec[1], "default": spec[2]}
        for token, spec in PALETTE.items()
    ]


def set_theme(
    db: Session,
    *,
    user: User,
    colors: Any = None,
    branding: Any = None,
    reset: bool = False,
) -> dict[str, Any]:
    if reset:
        row = _row(db)
        if row is not None:
            db.delete(row)
        audit.record(
            db,
            action=AuditAction.ADMIN_ACTION,
            org_id=user.org_id,
            actor_user_id=user.id,
            actor_email=user.email,
            target_type="theme",
            meta={"reset": True},
        )
        db.flush()
        return get_theme(db)

    current = get_theme(db)
    next_colors = _clean_colors({**current["colors"], **(colors or {})})
    next_branding = _clean_branding({**current["branding"], **(branding or {})})
    payload = {
        "colors": next_colors,
        "branding": next_branding,
        "updated_at": _now(),
        "updated_by": user.email,
    }
    row = _row(db)
    if row is None:
        db.add(SystemSetting(key=SETTING_KEY, value=payload, description="Runtime visual identity"))
    else:
        row.value = payload
        row.updated_by = user.id
    audit.record(
        db,
        action=AuditAction.ADMIN_ACTION,
        org_id=user.org_id,
        actor_user_id=user.id,
        actor_email=user.email,
        target_type="theme",
        meta={"colors": next_colors, "branding": next_branding},
    )
    db.flush()
    return get_theme(db)


def _now() -> str:
    return datetime.now(UTC).isoformat()
