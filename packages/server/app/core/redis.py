"""Redis connection management."""

from __future__ import annotations

import redis.asyncio as redis

from app.core.config import get_settings

settings = get_settings()

_redis_pool: redis.Redis | None = None


async def get_redis() -> redis.Redis:
    """Get or create the Redis connection."""
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = redis.from_url(
            settings.redis_url,
            decode_responses=True,
        )
    return _redis_pool


async def close_redis() -> None:
    """Close the Redis connection pool."""
    global _redis_pool
    if _redis_pool is not None:
        await _redis_pool.close()
        _redis_pool = None
