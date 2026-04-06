"""
app/core/redis_client.py — Redis connection pool using redis-py async client.
"""
from __future__ import annotations

import redis.asyncio as aioredis

from app.config import settings

# Module-level singleton pool (created on first import)
_redis_pool: aioredis.Redis | None = None


def get_redis_pool() -> aioredis.Redis:
    """Return (or create) the module-level Redis connection pool."""
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=20,
        )
    return _redis_pool


async def close_redis_pool() -> None:
    """Close all connections in the pool — called on app shutdown."""
    global _redis_pool
    if _redis_pool is not None:
        await _redis_pool.aclose()
        _redis_pool = None


# ── Convenience helpers ───────────────────────────────────────────
async def redis_ping() -> bool:
    """Return True if Redis is reachable."""
    try:
        r = get_redis_pool()
        return await r.ping()
    except Exception:
        return False
