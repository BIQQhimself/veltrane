"""Live-session presence for session-bound automation.

Tier 1 automation may only trade while the subscriber has the platform open. The workspace
posts a heartbeat while a page is visible and the key expires on its own, so a closed tab, a
crashed browser or a dropped connection all end the session without a cleanup call.

Redis is the store. When it cannot answer, the result is "not present": a presence check that
fails must stop automation, never start it.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from app.core.redis_client import cache_delete, get_json, set_json

log = logging.getLogger(__name__)

# Two missed heartbeats (the client sends one every 45 s) end the session.
PRESENCE_TTL_SECONDS = 120
_KEY = "presence:org:{org_id}"


def touch(org_id: str, *, surface: str = "workspace") -> dict:
    """Record that the subscriber is on the platform right now."""
    now = datetime.now(UTC)
    payload = {"org_id": org_id, "surface": surface, "seen_at": now.isoformat()}
    set_json(_KEY.format(org_id=org_id), payload, PRESENCE_TTL_SECONDS)
    return payload


def last_seen(org_id: str) -> dict | None:
    return get_json(_KEY.format(org_id=org_id))


def is_online(org_id: str) -> bool:
    return last_seen(org_id) is not None


def clear(org_id: str) -> None:
    cache_delete(_KEY.format(org_id=org_id))
