import asyncio
import json
import time
from typing import Optional, Callable, Awaitable

from new.config import settings


class RedisPipelineQueue:
    """Redis-backed work queue for serializing pipeline runs.

    Uses Redis lists (LPUSH/BRPOP) to create a FIFO queue. This prevents
    overlapping runs and allows the system to gracefully handle bursts
    of extraction requests. Falls back to direct execution when Redis
    is unavailable or disabled.
    """

    def __init__(self, redis_client=None):
        self._redis = redis_client
        self._worker_task: Optional[asyncio.Task] = None
        self._handler: Optional[Callable[[str], Awaitable[None]]] = None
        self._running = False

    def set_handler(self, handler: Callable[[str], Awaitable[None]]):
        self._handler = handler

    async def enqueue(self, run_id: str) -> bool:
        """Push a run_id onto the work queue. Returns True if queued."""
        if not self._redis or not settings.redis_enabled:
            return False
        try:
            await self._redis.lpush(settings.redis_queue_key, run_id)
            return True
        except Exception:
            return False

    async def dequeue(self, timeout: int = 5) -> Optional[str]:
        """Pop a run_id from the queue (blocking)."""
        if not self._redis or not settings.redis_enabled:
            return None
        try:
            _, value = await self._redis.brpop(
                settings.redis_queue_key, timeout=timeout
            )
            return value.decode() if isinstance(value, bytes) else value
        except Exception:
            return None

    async def queue_length(self) -> int:
        if not self._redis or not settings.redis_enabled:
            return 0
        try:
            return await self.llen(settings.redis_queue_key)
        except Exception:
            return 0

    async def start_worker(self):
        """Start a background worker that processes queued runs sequentially."""
        if self._worker_task is not None:
            return
        self._running = True
        self._worker_task = asyncio.create_task(self._worker_loop())

    async def _worker_loop(self):
        while self._running:
            run_id = await self.dequeue(timeout=3)
            if run_id and self._handler:
                try:
                    await self._handler(run_id)
                except Exception as e:
                    print(f"[Queue] Handler failed for {run_id}: {e}")
            await asyncio.sleep(0.1)

    async def stop_worker(self):
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            self._worker_task = None


class InMemoryRunGate:
    """Simple in-process semaphore gate to prevent overlapping runs when
    Redis is not available. Ensures only one pipeline runs at a time."""

    def __init__(self, max_concurrent: int = 1):
        self._sem = asyncio.Semaphore(max_concurrent)

    async def acquire(self) -> bool:
        return await self._sem.acquire()

    def release(self):
        self._sem.release()

    @property
    def locked(self) -> bool:
        return self._sem.locked()


_run_gate = InMemoryRunGate(max_concurrent=1)
_queue: Optional[RedisPipelineQueue] = None


def get_queue(redis_client=None) -> RedisPipelineQueue:
    global _queue
    if _queue is None:
        _queue = RedisPipelineQueue(redis_client)
    return _queue


def get_run_gate() -> InMemoryRunGate:
    return _run_gate
