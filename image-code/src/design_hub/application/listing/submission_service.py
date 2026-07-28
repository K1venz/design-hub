import time
from collections.abc import Callable
from dataclasses import dataclass, field
from uuid import uuid4

from design_hub.application.listing.requests import (
    CloneRequest,
    EditRequest,
    ListingGenerateRequest,
)
from design_hub.application.listing.task_planner import ListingTaskPlanner
from design_hub.application.tasking.health import (
    AdmissionResult,
    QueueAdmissionController,
    QueueSnapshotReader,
    RedisHealthState,
)
from design_hub.domain.enums import ModelName
from design_hub.domain.errors import NotFoundError
from design_hub.ports.generation_work import GenerationWorkRepository
from design_hub.ports.listing_query import ListingHistoryQuery
from design_hub.ports.upload_store import owns


def _new_id() -> str:
    return uuid4().hex


@dataclass(frozen=True)
class SubmissionReceipt:
    job_id: str
    queue_state: str
    estimated_wait_seconds: int
    replayed: bool


@dataclass(frozen=True)
class ListingSubmissionService:
    planner: ListingTaskPlanner
    repository: GenerationWorkRepository
    query: ListingHistoryQuery
    redis_health: RedisHealthState
    queue_snapshots: QueueSnapshotReader
    admission: QueueAdmissionController
    clock: Callable[[], float] = time.monotonic
    id_factory: Callable[[], str] = field(default=_new_id)

    async def submit_generate(
        self,
        *,
        user_id: str,
        request: ListingGenerateRequest,
        idempotency_key: str,
        trace_id: str,
        request_id: str,
        model: ModelName = ModelName.GPT_IMAGE_2,
    ) -> SubmissionReceipt:
        self._require_idempotency_key(idempotency_key)
        self._require_owned_uploads(user_id, tuple(request.upload_ids))
        admission = await self._admit()
        submission = self.planner.plan_generate(
            user_id=user_id,
            request=request,
            job_id=self.id_factory(),
            idempotency_key=idempotency_key,
            trace_id=trace_id,
            request_id=request_id,
            model=model,
        )
        result = await self.repository.submit(submission)
        return SubmissionReceipt(
            job_id=result.job_id,
            queue_state=admission.state,
            estimated_wait_seconds=admission.estimated_wait_seconds,
            replayed=result.replayed,
        )

    async def submit_clone(
        self,
        *,
        user_id: str,
        request: CloneRequest,
        idempotency_key: str,
        trace_id: str,
        request_id: str,
        model: ModelName = ModelName.GPT_IMAGE_2,
    ) -> SubmissionReceipt:
        self._require_idempotency_key(idempotency_key)
        self._require_owned_uploads(
            user_id,
            (
                *request.product_upload_ids,
                *request.reference_upload_ids,
            ),
        )
        admission = await self._admit()
        submission = self.planner.plan_clone(
            user_id=user_id,
            request=request,
            job_id=self.id_factory(),
            idempotency_key=idempotency_key,
            trace_id=trace_id,
            request_id=request_id,
            model=model,
        )
        result = await self.repository.submit(submission)
        return SubmissionReceipt(
            job_id=result.job_id,
            queue_state=admission.state,
            estimated_wait_seconds=admission.estimated_wait_seconds,
            replayed=result.replayed,
        )

    async def submit_edit(
        self,
        *,
        user_id: str,
        request: EditRequest,
        idempotency_key: str,
        trace_id: str,
        request_id: str,
        model: ModelName = ModelName.GPT_IMAGE_2,
    ) -> SubmissionReceipt:
        self._require_idempotency_key(idempotency_key)
        admission = await self._admit()
        source = await self.query.resolve_edit_source(
            source_image_key=request.source_image_key,
            user_id=user_id,
        )
        if source is None:
            raise NotFoundError(
                f"source image does not exist or is not owned: {request.source_image_key}"
            )
        submission = self.planner.plan_edit(
            user_id=user_id,
            request=request,
            source=source,
            job_id=self.id_factory(),
            idempotency_key=idempotency_key,
            trace_id=trace_id,
            request_id=request_id,
            model=model,
        )
        result = await self.repository.submit(submission)
        return SubmissionReceipt(
            job_id=result.job_id,
            queue_state=admission.state,
            estimated_wait_seconds=admission.estimated_wait_seconds,
            replayed=result.replayed,
        )

    async def _admit(self) -> AdmissionResult:
        self.redis_health.require_available(now=self.clock())
        snapshot = await self.queue_snapshots.snapshot()
        return self.admission.evaluate(
            queue_depth=snapshot.depth,
            rolling_item_seconds=snapshot.rolling_item_seconds,
            available_slots=snapshot.available_slots,
        )

    @staticmethod
    def _require_idempotency_key(value: str) -> None:
        if not value or value.isspace() or len(value) > 128:
            raise ValueError("Idempotency-Key must contain 1 to 128 characters")

    @staticmethod
    def _require_owned_uploads(user_id: str, upload_keys: tuple[str, ...]) -> None:
        if any(not owns(key, user_id) for key in upload_keys):
            raise NotFoundError("an input image does not exist or is not owned")
