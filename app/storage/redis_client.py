from typing import Optional

import redis.asyncio as redis

from app.settings import Settings


_redis: Optional[redis.Redis] = None


async def init_redis(settings: Settings) -> None:
    global _redis
    if _redis is None:
        _redis = redis.from_url(settings.redis_url, decode_responses=True)


async def get_redis() -> redis.Redis:
    if _redis is None:
        raise RuntimeError("Redis is not initialized. Call init_redis() first.")
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None