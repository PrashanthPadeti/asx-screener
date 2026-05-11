"""
ASX Screener — Redis Cache Layer
==================================
Fault-tolerant Redis cache. If Redis is unavailable the app degrades
gracefully — all cache operations become no-ops.

Usage:
    from app.core.cache import cache_get, cache_set, cache_delete, make_key

    # In a route:
    key  = make_key("screener", body_hash)
    hit  = await cache_get(key)
    if hit:
        return hit
    result = expensive_query()
    await cache_set(key, result, ttl=300)
    return result

TTL constants (seconds):
    SCREENER_TTL  = 300   — 5 min  (live screener results)
    COMPANY_TTL   = 600   — 10 min (company summary/overview)
    MARKET_TTL    = 120   — 2 min  (market snapshot/movers)
    STATIC_TTL    = 3600  — 1 hr   (indices, fund prices, commodities)
"""
import json
import logging
from typing import Any, Optional

from app.core.config import settings

log = logging.getLogger(__name__)

# TTL constants (seconds)
SCREENER_TTL = 300
COMPANY_TTL  = 600
MARKET_TTL   = 120
STATIC_TTL   = 3600

_redis = None
_redis_ok = True   # flips to False on first connection failure; retried each call


def _get_client():
    """Lazy singleton Redis client. Returns None if unavailable."""
    global _redis, _redis_ok
    if _redis is not None:
        return _redis
    if not _redis_ok:
        # Back-off: re-attempt every call (cheap check)
        pass
    try:
        import redis.asyncio as aioredis
        _redis = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        _redis_ok = True
        log.info("Redis connected: %s", settings.REDIS_URL)
        return _redis
    except Exception as e:
        log.warning("Redis unavailable — caching disabled: %s", e)
        _redis_ok = False
        return None


def make_key(*parts: str) -> str:
    """Build a namespaced cache key: 'asx:<part1>:<part2>:...'"""
    return "asx:" + ":".join(str(p) for p in parts)


async def cache_get(key: str) -> Optional[Any]:
    """Return cached value (deserialized JSON) or None on miss/error."""
    client = _get_client()
    if client is None:
        return None
    try:
        raw = await client.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as e:
        log.debug("cache_get error for %s: %s", key, e)
        return None


async def cache_set(key: str, value: Any, ttl: int = SCREENER_TTL) -> bool:
    """Serialize value to JSON and store with TTL. Returns True on success."""
    client = _get_client()
    if client is None:
        return False
    try:
        await client.setex(key, ttl, json.dumps(value, default=str))
        return True
    except Exception as e:
        log.debug("cache_set error for %s: %s", key, e)
        return False


async def cache_delete(key: str) -> bool:
    """Delete a cache key. Returns True on success."""
    client = _get_client()
    if client is None:
        return False
    try:
        await client.delete(key)
        return True
    except Exception as e:
        log.debug("cache_delete error for %s: %s", key, e)
        return False


async def cache_delete_pattern(pattern: str) -> int:
    """Delete all keys matching a pattern (uses SCAN — safe for production).
    Returns number of deleted keys."""
    client = _get_client()
    if client is None:
        return 0
    try:
        deleted = 0
        async for key in client.scan_iter(pattern):
            await client.delete(key)
            deleted += 1
        return deleted
    except Exception as e:
        log.debug("cache_delete_pattern error for %s: %s", pattern, e)
        return 0


async def cache_ping() -> bool:
    """Health check — returns True if Redis is reachable."""
    client = _get_client()
    if client is None:
        return False
    try:
        return await client.ping()
    except Exception:
        return False
