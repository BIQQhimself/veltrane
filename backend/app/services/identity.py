"""Public-facing identity for the account header and profile page.

A trader's display name and avatar colour are presentation only; they never grant anything.
The public id is derived from the user id so support can match an account without exposing the
database key, and it is stable for the life of the account.
"""

from __future__ import annotations

import re

from app.db.models import User

AVATAR_COLORS = [
    "#C8A96A",
    "#7F9F8C",
    "#8C7BB0",
    "#B06A6A",
    "#6E8CA8",
    "#A98F6B",
    "#7E9E9C",
    "#9B8AA6",
]
DEFAULT_AVATAR_COLOR = AVATAR_COLORS[0]
DISPLAY_NAME_MAX = 40
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def public_id(user: User) -> str:
    raw = (user.id or "").replace("-", "").upper()
    return f"VT-{raw[:8]}" if raw else "VT-UNKNOWN"


def display_name(user: User) -> str:
    stored = (user.preferences or {}).get("display_name")
    if isinstance(stored, str) and stored.strip():
        return stored.strip()
    full = (user.full_name or "").strip()
    return full.split(" ")[0] if full else "Trader"


def avatar_color(user: User) -> str:
    stored = (user.preferences or {}).get("avatar_color")
    if isinstance(stored, str) and _HEX.match(stored):
        return stored
    # Deterministic per account so the colour does not change between sessions.
    raw = (user.id or "0").replace("-", "")
    try:
        index = int(raw[:4], 16) % len(AVATAR_COLORS)
    except ValueError:
        index = 0
    return AVATAR_COLORS[index]


def identity(user: User) -> dict:
    return {
        "display_name": display_name(user),
        "full_name": user.full_name,
        "avatar_color": avatar_color(user),
        "public_id": public_id(user),
        "email": user.email,
    }


def clean_display_name(value: str) -> str:
    cleaned = " ".join((value or "").split())
    if len(cleaned) < 2:
        raise ValueError("Display name must be at least 2 characters.")
    if len(cleaned) > DISPLAY_NAME_MAX:
        raise ValueError(f"Display name must be at most {DISPLAY_NAME_MAX} characters.")
    if not all(char.isprintable() for char in cleaned):
        raise ValueError("Display name contains characters that cannot be displayed.")
    return cleaned


def clean_avatar_color(value: str) -> str:
    if not _HEX.match(value or ""):
        raise ValueError("Avatar colour must be a six-digit hex value such as #C8A96A.")
    return value.lower()
