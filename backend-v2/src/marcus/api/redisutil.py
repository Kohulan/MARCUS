"""Async Redis helpers shared by the rate limiter (marcus.api.security) and the event-stream
slots (marcus.api.routes.events)."""

import redis.asyncio as aioredis


async def incr_with_ttl(redis: aioredis.Redis, key: str, ttl: int) -> int:
    """INCR `key` and give it a `ttl` seconds expiry, in one round trip; returns the new count.
    Redis errors are the caller's to handle."""
    async with redis.pipeline(transaction=True) as pipe:
        pipe.incr(key)
        pipe.expire(key, ttl)
        count, _ = await pipe.execute()
    return count
