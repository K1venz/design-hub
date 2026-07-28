import asyncio
import logging
from dataclasses import dataclass, field

from design_hub.application.tasking.outbox_dispatcher import OutboxDispatcher
from design_hub.application.tasking.worker import GenerationWorker
from design_hub.ports.task_broker import Delivery, TaskBroker

logger = logging.getLogger(__name__)


@dataclass
class GenerationWorkerRuntime:
    dispatcher: OutboxDispatcher
    broker: TaskBroker
    worker: GenerationWorker
    consumer_name: str
    read_count: int = 8
    read_block_ms: int = 1000
    reclaim_idle_ms: int = 30_000
    dispatcher_interval_seconds: float = 0.2
    shutdown_timeout_seconds: float = 30
    _active: set[asyncio.Task[None]] = field(default_factory=set, init=False)

    def __post_init__(self) -> None:
        if self.read_count <= 0:
            raise ValueError("read_count must be positive")

    async def run(self, stop: asyncio.Event) -> None:
        await self.broker.ensure_group()
        dispatcher_task = asyncio.create_task(self._dispatch_loop(stop))
        consumer_task = asyncio.create_task(self._consume_loop(stop))
        stop_task = asyncio.create_task(stop.wait())
        service_tasks = {dispatcher_task, consumer_task}
        try:
            done, _pending = await asyncio.wait(
                {*service_tasks, stop_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            failed = next(
                (
                    task
                    for task in done
                    if task in service_tasks
                    and not task.cancelled()
                    and task.exception() is not None
                ),
                None,
            )
            if failed is not None:
                stop.set()
                await failed
        finally:
            stop.set()
            stop_task.cancel()
            for task in service_tasks:
                task.cancel()
            await asyncio.gather(
                stop_task,
                *service_tasks,
                return_exceptions=True,
            )
            await self._drain_active()

    async def _dispatch_loop(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            await self.dispatcher.dispatch_once()
            try:
                await asyncio.wait_for(
                    stop.wait(),
                    timeout=self.dispatcher_interval_seconds,
                )
            except TimeoutError:
                continue

    async def _consume_loop(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            await self._wait_for_capacity(stop)
            if stop.is_set():
                return
            capacity = self.read_count - len(self._active)
            reclaimed = await self.broker.autoclaim(
                consumer=self.consumer_name,
                min_idle_ms=self.reclaim_idle_ms,
                count=capacity,
            )
            self._schedule(reclaimed)
            await self._wait_for_capacity(stop)
            if stop.is_set():
                return
            capacity = self.read_count - len(self._active)
            deliveries = await self.broker.read(
                consumer=self.consumer_name,
                count=capacity,
                block_ms=self.read_block_ms,
            )
            self._schedule(deliveries)

    async def _wait_for_capacity(self, stop: asyncio.Event) -> None:
        while len(self._active) >= self.read_count and not stop.is_set():
            stop_task = asyncio.create_task(stop.wait())
            done, _pending = await asyncio.wait(
                {*self._active, stop_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if stop_task not in done:
                stop_task.cancel()
                await asyncio.gather(stop_task, return_exceptions=True)

    def _schedule(self, deliveries: tuple[Delivery, ...]) -> None:
        for delivery in deliveries:
            task = asyncio.create_task(self.worker.process(delivery))
            self._active.add(task)
            task.add_done_callback(self._delivery_finished)

    def _delivery_finished(self, task: asyncio.Task[None]) -> None:
        self._active.discard(task)
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            logger.error(
                "generation_delivery_failed",
                extra={"error_type": type(error).__name__},
            )

    async def _drain_active(self) -> None:
        if not self._active:
            return
        done, pending = await asyncio.wait(
            self._active,
            timeout=self.shutdown_timeout_seconds,
        )
        del done
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
