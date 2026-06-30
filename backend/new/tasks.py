import asyncio
from typing import Optional

from loguru import logger

from new.pipeline import Pipeline
from new.run_queue import get_queue, get_run_gate, RedisPipelineQueue
from new.config import settings


class TaskManager:
    def __init__(self):
        self._tasks: dict[str, asyncio.Task] = {}
        self._pipelines: dict[str, Pipeline] = {}
        self._queue: Optional[RedisPipelineQueue] = None
        self._gate = get_run_gate()

    def set_queue(self, queue: RedisPipelineQueue):
        self._queue = queue
        queue.set_handler(self._execute_queued_run)

    async def _execute_queued_run(self, run_id: str):
        pipeline = self._pipelines.get(run_id)
        if pipeline:
            logger.info("TaskManager: executing queued run {}", run_id)
            await pipeline.execute(run_id)

    def start_run(self, run_id: str, pipeline: Pipeline):
        self._pipelines[run_id] = pipeline

        if self._queue and settings.redis_enabled:
            task = asyncio.create_task(self._start_queued(run_id, pipeline))
        else:
            task = asyncio.create_task(self._start_gated(run_id, pipeline))

        self._tasks[run_id] = task
        task.add_done_callback(lambda t: self._tasks.pop(run_id, None))
        logger.info("TaskManager: scheduled run {} (task {})", run_id, id(task))

    async def _start_queued(self, run_id: str, pipeline: Pipeline):
        try:
            queued = await self._queue.enqueue(run_id)
            if not queued:
                logger.info("TaskManager: running {} directly (queue unavailable)", run_id)
                await pipeline.execute(run_id)
        finally:
            self._tasks.pop(run_id, None)
            self._pipelines.pop(run_id, None)

    async def _start_gated(self, run_id: str, pipeline: Pipeline):
        logger.info("TaskManager: acquiring gate for run {}", run_id)
        await self._gate.acquire()
        logger.info("TaskManager: gate acquired for run {}", run_id)
        try:
            await pipeline.execute(run_id)
        finally:
            self._gate.release()
            self._tasks.pop(run_id, None)
            self._pipelines.pop(run_id, None)
            logger.info("TaskManager: gate released and cleaned up for run {}", run_id)

    def pause_run(self, run_id: str) -> bool:
        pipeline = self._pipelines.get(run_id)
        if pipeline:
            pipeline.request_pause()
            return True
        return False

    def resume_run(self, run_id: str) -> bool:
        pipeline = self._pipelines.get(run_id)
        if pipeline:
            pipeline.request_resume()
            return True
        return False

    def stop_run(self, run_id: str) -> bool:
        pipeline = self._pipelines.get(run_id)
        if pipeline:
            pipeline.request_stop()
            return True
        return False

    def is_running(self, run_id: str) -> bool:
        task = self._tasks.get(run_id)
        return task is not None and not task.done()

    async def cleanup(self):
        for run_id, task in self._tasks.items():
            if not task.done():
                task.cancel()
        self._tasks.clear()
        self._pipelines.clear()
        if self._queue:
            await self._queue.stop_worker()


task_manager = TaskManager()
