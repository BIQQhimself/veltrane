from __future__ import annotations

import threading
import time

from app.core.config import settings
from app.core.errors import too_many
from app.core.redis_client import get_redis
from fastapi import Request

_memory: dict[str, tuple[int, float]] = {}
_lock = threading.Lock()


def _memory_hit(key: str, limit: int, window: int) -> int:
    now = time.monotonic()
    with _lock:
        count, reset_at = _memory.get(key, (0, now + window))
        if now >= reset_at:
            count, reset_at = 0, now + window
        count += 1
        _memory[key] = (count, reset_at)
        return count


def hit(key: str, limit: int, window: int) -> int:
    client = get_redis()
    if client is not None:
        try:
            pipe = client.pipeline()
            pipe.incr(key)
            pipe.expire(key, window, nx=True)
            count, _ = pipe.execute()
            return int(count)
        except Exception:  # noqa: BLE001 - fall back to in-process limiter
            pass
    return _memory_hit(key, limit, window)


def client_ip(request: Request) -> str:
    """Caller address, honouring X-Forwarded-For only from a trusted proxy.

    Trusting the header unconditionally lets any client pick its own rate-limit
    bucket by sending a made-up value, which turns the login limiter into
    decoration. When the peer is not a configured proxy the header is ignored
    and every caller behind that peer shares one bucket.
    """
    peer = request.client.host if request.client else "unknown"
    if peer not in settings.trusted_proxy_ips:
        return peer

    forwarded = request.headers.get("x-forwarded-for")
    if not forwarded:
        return peer

    hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
    for hop in reversed(hops):
        if hop not in settings.trusted_proxy_ips:
            return hop
    return hops[0] if hops else peer


def enforce(request: Request, bucket: str, limit: int, window: int) -> None:
    ip = client_ip(request)
    key = f"rl:{bucket}:{ip}"
    if hit(key, limit, window) > limit:
        raise too_many("rate_limited", "Too many requests. Please slow down and try again shortly.")
