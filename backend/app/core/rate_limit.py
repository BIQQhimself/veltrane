from __future__ import annotations

import threading
import time

from fastapi import Request

from app.core.errors import too_many
from app.core.redis_client import get_redis

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
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def enforce(request: Request, bucket: str, limit: int, window: int) -> None:
    ip = client_ip(request)
    key = f"rl:{bucket}:{ip}"
    if hit(key, limit, window) > limit:
        raise too_many("rate_limited", "Too many requests. Please slow down and try again shortly.")
