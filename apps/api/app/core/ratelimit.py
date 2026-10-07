"""Fixed-window rate limiting in Valkey.

Fails open: if Valkey is unreachable the request is allowed and a warning is logged, because an outage of the
cache must not take the API down. Public, unauthenticated routes (M2) use stricter per-IP limits.
"""

import time
from dataclasses import dataclass

import structlog
from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RateDecision:
    allowed: bool
    retry_after_seconds: int


async def hit(valkey: Redis, key: str, *, limit: int, window_seconds: int = 60) -> RateDecision:
    window = int(time.time()) // window_seconds
    bucket = f"rl:{key}:{window}"
    try:
        async with valkey.pipeline(transaction=True) as pipe:
            pipe.incr(bucket)
            pipe.expire(bucket, window_seconds + 1, nx=True)
            count, _ = await pipe.execute()
    except (RedisError, OSError) as exc:
        logger.warning("rate_limit_unavailable", error=type(exc).__name__)
        return RateDecision(allowed=True, retry_after_seconds=0)
    if int(count) > limit:
        retry_after = window_seconds - int(time.time()) % window_seconds
        return RateDecision(allowed=False, retry_after_seconds=max(retry_after, 1))
    return RateDecision(allowed=True, retry_after_seconds=0)
