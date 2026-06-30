import asyncio
import time
import json
from collections import defaultdict
from typing import Optional
from urllib.parse import urlparse

from new.config import settings


class TokenBucket:
    def __init__(self, rate: float = 1.0, burst: int = 3):
        self.rate = rate
        self.burst = burst
        self.tokens = burst
        self.last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> float:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_refill
            self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
            self.last_refill = now
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return 0.0
            wait = (1.0 - self.tokens) / self.rate
            self.tokens = 0.0
            self.last_refill = now + wait
        await asyncio.sleep(wait)
        return wait


class DomainRateLimiter:
    def __init__(self, default_rate: float = 1.0):
        self._buckets: dict[str, TokenBucket] = {}
        self._default_rate = default_rate

    def _get_domain(self, url: str) -> str:
        return urlparse(url).hostname or "unknown"

    async def wait(self, url: str):
        domain = self._get_domain(url)
        if domain not in self._buckets:
            self._buckets[domain] = TokenBucket(rate=self._default_rate)
        await self._buckets[domain].acquire()


class RedisTokenBucket:
    """Redis-backed distributed token bucket for rate limiting.

    Uses Redis sorted sets to track request timestamps for sliding-window
    rate limiting. Falls back to in-memory token bucket if Redis is unavailable.
    """

    def __init__(self, redis_client=None):
        self._redis = redis_client
        self._local = TokenBucket(
            rate=settings.llm_rate_per_minute / 60.0,
            burst=settings.llm_burst_size,
        )

    async def acquire(self, key: str = "default") -> float:
        if not self._redis or not settings.redis_enabled:
            return await self._local.acquire()

        now = time.time()
        window = 60.0
        max_tokens = settings.llm_rate_per_minute

        try:
            pipe = self._redis.pipeline()
            pipe.zremrangebyscore(key, 0, now - window)
            pipe.zcard(key)
            count, = await pipe.execute()
            count_result = count[1] if isinstance(count, list) else count

            current_count = (
                count_result if isinstance(count_result, int) else int(count_result)
            )

            if current_count >= max_tokens:
                oldest = await self._redis.zrange(key, 0, 0, withscores=True)
                if oldest:
                    wait = oldest[0][1] + window - now
                    if wait > 0:
                        await asyncio.sleep(wait)
                        return wait

            await self._redis.zadd(key, {str(now): now})
            await self._redis.expire(key, 120)
            return 0.0
        except Exception:
            return await self._local.acquire()


class LLMRateLimiter:
    """Manages LLM token usage and rate limiting.

    Tracks cumulative token usage across runs and provides a distributed
    rate limit via Redis. Falls back to in-memory when Redis is off.
    """

    def __init__(self, redis_client=None):
        self._redis = redis_client
        self._bucket = RedisTokenBucket(redis_client)
        self._local_tokens: dict[str, int] = defaultdict(int)
        self._lock = asyncio.Lock()

    async def check_rate_limit(self, key: str = "llm:global") -> float:
        return await self._bucket.acquire(key)

    async def record_token_usage(self, tokens: int, key: str = "llm:global"):
        if self._redis and settings.redis_enabled:
            try:
                await self._redis.hincrby("llm:token_usage", key, tokens)
                total = await self._redis.hget("llm:token_usage", key)
                return int(total) if total else 0
            except Exception:
                pass
        async with self._lock:
            self._local_tokens[key] += tokens
            return self._local_tokens[key]

    async def get_token_usage(self, key: str = "llm:global") -> int:
        if self._redis and settings.redis_enabled:
            try:
                val = await self._redis.hget("llm:token_usage", key)
                return int(val) if val else 0
            except Exception:
                pass
        async with self._lock:
            return self._local_tokens.get(key, 0)

    async def reset(self, key: str = "llm:global"):
        if self._redis and settings.redis_enabled:
            try:
                await self._redis.hdel("llm:token_usage", key)
            except Exception:
                pass
        async with self._lock:
            self._local_tokens[key] = 0


_llm_rate_limiter: Optional[LLMRateLimiter] = None


def get_llm_rate_limiter(redis_client=None) -> LLMRateLimiter:
    global _llm_rate_limiter
    if _llm_rate_limiter is None:
        _llm_rate_limiter = LLMRateLimiter(redis_client)
    return _llm_rate_limiter
