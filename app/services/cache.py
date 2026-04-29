import json
from typing import Optional
import redis.asyncio as aioredis
from app.config import settings

_redis_client: Optional[aioredis.Redis] = None


async def get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


async def cache_get(key: str) -> Optional[dict]:
    client = await get_redis()
    raw = await client.get(key)
    if raw is None:
        return None
    return json.loads(raw)


async def cache_set(key: str, value: dict, ttl: int = None) -> None:
    client = await get_redis()
    ttl = ttl or settings.cache_ttl
    await client.setex(key, ttl, json.dumps(value, default=str))


async def cache_delete(key: str) -> None:
    client = await get_redis()
    await client.delete(key)


async def ping_redis() -> bool:
    try:
        client = await get_redis()
        return await client.ping()
    except Exception:
        return False
