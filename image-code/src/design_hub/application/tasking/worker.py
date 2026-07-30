import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Protocol, TypeVar

from design_hub.domain.admin import ModelOperation
from design_hub.domain.errors import DataInvariantError
from design_hub.domain.models import GeneratedImage, ReferenceImage
from design_hub.domain.tasking import (
    GenerationItemStatus,
    RenderTier,
    is_terminal,
)
from design_hub.infrastructure.monitoring.logging import (
    capture_task_exception,
)
from design_hub.infrastructure.monitoring.task_metrics import task_metrics
from design_hub.ports.generation_work import (
    GenerationWorkItem,
    GenerationWorkRepository,
)
from design_hub.ports.model_calls import ModelCallContext
from design_hub.ports.model_provider import ProviderError, ReferenceMode
from design_hub.ports.provider_execution import (
    ImmediateResult,
    ProviderExecutor,
    ProviderRequest,
    SubmissionUncertain,
    SubmittedTask,
)
from design_hub.ports.task_broker import Delivery, TaskBroker

logger = logging.getLogger(__name__)
_T = TypeVar("_T")


class ReferenceMaterializer(Protocol):
    async def materialize(
        self, work: GenerationWorkItem, reference_mode: ReferenceMode
    ) -> tuple[ReferenceImage, ...]: ...


class ProviderSlots(Protocol):
    async def acquire(self, *, worker_id: str, item_id: str) -> bool: ...

    async def release(self, *, worker_id: str, item_id: str) -> bool: ...

    async def refresh(self, *, worker_id: str, item_id: str) -> bool: ...


class GenerationWorker:
    def __init__(
        self,
        *,
        repository: GenerationWorkRepository,
        broker: TaskBroker,
        executor_for: Callable[[object], ProviderExecutor],
        materializer: ReferenceMaterializer,
        slots_for: Callable[[object, RenderTier], ProviderSlots],
        worker_id: str,
        lease_seconds: int,
        heartbeat_seconds: float = 15,
        slot_refresh_seconds: float = 10,
    ) -> None:
        if heartbeat_seconds <= 0 or slot_refresh_seconds <= 0:
            raise ValueError("lease refresh intervals must be positive")
        self._repository = repository
        self._broker = broker
        self._executor_for = executor_for
        self._materializer = materializer
        self._slots_for = slots_for
        self._worker_id = worker_id
        self._lease_seconds = lease_seconds
        self._heartbeat_seconds = heartbeat_seconds
        self._slot_refresh_seconds = slot_refresh_seconds

    async def process(self, delivery: Delivery) -> None:
        message = delivery.message
        work = await self._repository.load_item(message.item_id)
        self._require_matching_snapshot(work, delivery)
        if is_terminal(work.status):
            logger.info(
                "generation_item_duplicate_terminal",
                extra=self._log_context(delivery, work),
            )
            await self._broker.ack(delivery.redis_id)
            return
        recoverable = {
            GenerationItemStatus.QUEUED,
            GenerationItemStatus.CLAIMED,
            GenerationItemStatus.SUBMITTING,
            GenerationItemStatus.SUBMITTED,
            GenerationItemStatus.PROCESSING,
            GenerationItemStatus.STORING,
        }
        if work.status not in recoverable:
            raise DataInvariantError(
                f"generation item {work.spec.item_id} cannot start from {work.status}"
            )

        await self._repository.claim(
            work.spec.item_id,
            self._worker_id,
            self._lease_seconds,
        )
        if work.status is GenerationItemStatus.STORING:
            await self._repository.fail_item(
                work.spec.item_id,
                self._worker_id,
                "storage_commit_uncertain",
                "Worker lease expired while committing the generated image",
            )
            logger.error(
                "generation_stale_storage_failed_closed",
                extra=self._log_context(delivery, work),
            )
            task_metrics.record_failure("storage_commit_uncertain")
            await self._broker.ack(delivery.redis_id)
            return
        if work.status is GenerationItemStatus.SUBMITTING:
            await self._repository.mark_submission_uncertain(
                work.spec.item_id,
                self._worker_id,
                "Worker lease expired while provider submission outcome was unknown",
            )
            logger.error(
                "generation_stale_submission_marked_uncertain",
                extra=self._log_context(delivery, work),
            )
            task_metrics.record_uncertain(work.spec.model.value)
            await self._broker.ack(delivery.redis_id)
            return

        executor = self._executor_for(work.spec.model)
        references = await self._materializer.materialize(
            work, executor.reference_mode
        )
        request = ProviderRequest(
            context=ModelCallContext(
                user_id=work.user_id,
                operation=self._model_operation(references),
                job_id=work.job_id,
                generation_item_id=work.spec.item_id,
            ),
            prompt=work.spec.final_prompt,
            reference_images=references,
            size=work.spec.size,
            seed=work.spec.seed,
            quality=work.spec.quality,
        )

        if work.status in {
            GenerationItemStatus.SUBMITTED,
            GenerationItemStatus.PROCESSING,
        }:
            if work.provider_task_id is None:
                raise DataInvariantError(
                    f"recoverable item {work.spec.item_id} has no provider task id"
                )
            if work.status is GenerationItemStatus.SUBMITTED:
                await self._repository.mark_processing(
                    work.spec.item_id,
                    self._worker_id,
                )
            try:
                image = await self._guard_operation(
                    executor.resume(work.provider_task_id, request),
                    work,
                    slots=None,
                )
            except ProviderError as exc:
                await self._fail_provider(work, delivery, exc)
                return
            await self._store_and_complete(work, delivery, image)
            return

        slots = self._slots_for(work.spec.model, work.spec.render_tier)
        acquired = await slots.acquire(
            worker_id=self._worker_id,
            item_id=work.spec.item_id,
        )
        if not acquired:
            logger.info(
                "generation_provider_slot_unavailable",
                extra=self._log_context(delivery, work),
            )
            return

        try:
            await self._repository.mark_submitting(
                work.spec.item_id,
                self._worker_id,
            )
            logger.info(
                "generation_provider_submit_started",
                extra=self._log_context(delivery, work),
            )
            try:
                task_metrics.provider_started(
                    work.spec.model.value,
                    work.spec.render_tier.value,
                )
                try:
                    outcome = await self._guard_operation(
                        executor.submit(
                            request,
                            operation_id=work.spec.operation_id,
                        ),
                        work,
                        slots=slots,
                    )
                finally:
                    task_metrics.provider_finished(
                        work.spec.model.value,
                        work.spec.render_tier.value,
                    )
            except SubmissionUncertain as exc:
                await self._repository.mark_submission_uncertain(
                    work.spec.item_id,
                    self._worker_id,
                    str(exc),
                )
                logger.error(
                    "generation_provider_submission_uncertain",
                    extra=self._log_context(delivery, work),
                    exc_info=True,
                )
                task_metrics.record_uncertain(work.spec.model.value)
                capture_task_exception(
                    exc,
                    request_id=delivery.message.request_id,
                    job_id=work.job_id,
                    item_id=work.spec.item_id,
                    provider=work.spec.model.value,
                    error_code="submission_uncertain",
                )
                await self._broker.ack(delivery.redis_id)
                return
            except ProviderError as exc:
                await self._fail_provider(work, delivery, exc)
                return

            if isinstance(outcome, SubmittedTask):
                await self._repository.mark_submitted(
                    work.spec.item_id,
                    self._worker_id,
                    outcome.provider_task_id,
                )
                await slots.release(
                    worker_id=self._worker_id,
                    item_id=work.spec.item_id,
                )
                acquired = False
                await self._repository.mark_processing(
                    work.spec.item_id,
                    self._worker_id,
                )
                try:
                    image = await self._guard_operation(
                        executor.resume(outcome.provider_task_id, request),
                        work,
                        slots=None,
                    )
                except ProviderError as exc:
                    await self._fail_provider(work, delivery, exc)
                    return
            elif isinstance(outcome, ImmediateResult):
                image = outcome.image
            else:
                raise DataInvariantError(
                    f"unsupported provider outcome: {type(outcome).__name__}"
                )

            await self._store_and_complete(work, delivery, image)
        finally:
            if acquired:
                await slots.release(
                    worker_id=self._worker_id,
                    item_id=work.spec.item_id,
                )

    async def _guard_operation(
        self,
        operation: Awaitable[_T],
        work: GenerationWorkItem,
        *,
        slots: ProviderSlots | None,
    ) -> _T:
        operation_task = asyncio.ensure_future(operation)
        guard_tasks = {
            asyncio.create_task(self._heartbeat_loop(work)),
        }
        if slots is not None:
            guard_tasks.add(
                asyncio.create_task(self._slot_refresh_loop(work, slots))
            )
        try:
            done, _pending = await asyncio.wait(
                {operation_task, *guard_tasks},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if operation_task in done:
                return await operation_task
            guard = next(iter(done))
            await guard
            raise DataInvariantError("lease guard stopped unexpectedly")
        finally:
            operation_task.cancel()
            for task in guard_tasks:
                task.cancel()
            with suppress(asyncio.CancelledError):
                await operation_task
            await asyncio.gather(*guard_tasks, return_exceptions=True)

    async def _heartbeat_loop(self, work: GenerationWorkItem) -> None:
        while True:
            await asyncio.sleep(self._heartbeat_seconds)
            await self._repository.heartbeat(
                work.spec.item_id,
                self._worker_id,
                self._lease_seconds,
            )

    async def _slot_refresh_loop(
        self,
        work: GenerationWorkItem,
        slots: ProviderSlots,
    ) -> None:
        while True:
            await asyncio.sleep(self._slot_refresh_seconds)
            refreshed = await slots.refresh(
                worker_id=self._worker_id,
                item_id=work.spec.item_id,
            )
            if not refreshed:
                raise DataInvariantError(
                    f"provider slot lease lost for item {work.spec.item_id}"
                )

    async def _fail_provider(
        self,
        work: GenerationWorkItem,
        delivery: Delivery,
        error: ProviderError,
    ) -> None:
        await self._repository.fail_item(
            work.spec.item_id,
            self._worker_id,
            type(error).__name__,
            str(error),
        )
        error_code = type(error).__name__
        task_metrics.record_failure(error_code)
        capture_task_exception(
            error,
            request_id=delivery.message.request_id,
            job_id=work.job_id,
            item_id=work.spec.item_id,
            provider=work.spec.model.value,
            error_code=error_code,
        )
        logger.warning(
            "generation_provider_failed",
            extra=self._log_context(delivery, work),
            exc_info=True,
        )
        await self._broker.ack(delivery.redis_id)

    async def _store_and_complete(
        self,
        work: GenerationWorkItem,
        delivery: Delivery,
        image: GeneratedImage,
    ) -> None:
        await self._repository.mark_storing(
            work.spec.item_id,
            self._worker_id,
        )
        await self._repository.complete_item(
            work.spec.item_id,
            self._worker_id,
            image,
        )
        logger.info(
            "generation_item_completed",
            extra=self._log_context(delivery, work),
        )
        task_metrics.observe_item_duration(
            "generated",
            max(image.latency_ms, 0) / 1000,
        )
        await self._broker.ack(delivery.redis_id)

    @staticmethod
    def _require_matching_snapshot(
        work: GenerationWorkItem, delivery: Delivery
    ) -> None:
        message = delivery.message
        persisted = (
            work.job_id,
            work.user_id,
            work.spec.item_id,
            work.spec.operation_id,
            work.spec.operation_type,
        )
        routed = (
            message.job_id,
            message.user_id,
            message.item_id,
            message.operation_id,
            message.operation_type,
        )
        if persisted != routed:
            raise DataInvariantError(
                f"task message does not match persisted item {message.item_id}"
            )

    @staticmethod
    def _model_operation(
        references: tuple[ReferenceImage, ...],
    ) -> ModelOperation:
        if references:
            return ModelOperation.IMAGE_EDIT
        return ModelOperation.IMAGE_GENERATION

    def _log_context(
        self, delivery: Delivery, work: GenerationWorkItem
    ) -> dict[str, object]:
        return {
            "trace_id": delivery.message.trace_id,
            "request_id": delivery.message.request_id,
            "message_id": delivery.message.message_id,
            "redis_id": delivery.redis_id,
            "job_id": work.job_id,
            "item_id": work.spec.item_id,
            "operation_id": work.spec.operation_id,
            "provider_task_id": work.provider_task_id,
            "worker_id": self._worker_id,
            "status": work.status.value,
        }
