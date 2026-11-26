from __future__ import annotations

import logging
from typing import Any

import redis
from app.core.config import settings
from redis.exceptions import RedisError

log = logging.getLogger(__name__)
_client: redis.Redis | None = None


def get_redis() -> redis.Redis | None:
    """Return a Redis client, or None when unavailable (the app degrades gracefully)."""
    global _client
    if _client is not None:
        return _client
    try:
        client = redis.Redis.from_url(settings.redis_url, decode_responses=True, socket_timeout=1.0)
        client.ping()
        _client = client
    except (RedisError, OSError) as exc:
        log.warning("redis_unavailable", extra={"extra_fields": {"error": str(exc)}})
        _client = None
    return _client


def cache_get(key: str) -> str | None:
    client = get_redis()
    if not client:
        return None
    try:
        return client.get(key)
    except RedisError:
        return None


def cache_set(key: str, value: str, ttl: int) -> None:
    client = get_redis()
    if not client:
        return
    try:
        client.set(key, value, ex=ttl)
    except RedisError:
        pass


def cache_delete(key: str) -> None:
    client = get_redis()
    if not client:
        return
    try:
        client.delete(key)
    except RedisError:
        pass


def set_json(key: str, value: dict[str, Any], ttl: int) -> None:
    import json

    cache_set(key, json.dumps(value, default=str), ttl)


def get_json(key: str) -> dict[str, Any] | None:
    import json

    raw = cache_get(key)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None
