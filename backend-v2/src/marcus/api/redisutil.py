"""Async Redis helpers shared by the rate limiter (marcus.api.security) and the event-stream
slots (marcus.api.routes.events)."""

import redis.asyncio as aioredis


async def incr_with_ttl(redis: aioredis.Redis, key: str, ttl: int, *, first_only=False) -> int:
    """INCR `key` and give it a `ttl` seconds expiry, in one round trip; returns the new count.
    Redis errors are the caller's to handle.

    `first_only=True` (a key that names its own fixed window): the expiry is set by the first
    INCR only (EXPIRE NX, Redis >= 7) and the two commands go without MULTI/EXEC. Otherwise
    every call renews the expiry, atomically with the INCR (a counter that is also DECRed
    must never lose its expiry)."""
    async with redis.pipeline(transaction=not first_only) as pipe:
        pipe.incr(key)
        pipe.expire(key, ttl, nx=first_only)
        count, _ = await pipe.execute()
    return count
