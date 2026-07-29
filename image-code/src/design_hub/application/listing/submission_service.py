import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from uuid import uuid4

from design_hub.application.listing.background_replacement import (
    closest_supported_ratio,
)
from design_hub.application.listing.listing_service import build_listing_prompts
from design_hub.application.listing.prompt_composer import (
    compose_clone_prompt,
)
from design_hub.application.listing.requests import (
    BackgroundReplaceRequest,
    CloneRequest,
    EditRequest,
    ListingGenerateRequest,
)
from design_hub.application.listing.sizing import generation_size
from design_hub.application.listing.task_planner import ListingTaskPlanner
from design_hub.application.listing.upload_service import UploadService
from design_hub.application.tasking.health import (
    AdmissionRejected,
    AdmissionResult,
    QueueAdmissionController,
    QueueSnapshotReader,
    RedisHealthState,
)
from design_hub.domain.enums import ModelName
from design_hub.domain.errors import NotFoundError
from design_hub.ports.generation_work import (
    GenerationWorkRepository,
    JobSubmission,
)
from design_hub.ports.listing_query import ListingHistoryQuery
from design_hub.ports.upload_store import owns

logger = logging.getLogger(__name__)


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
    uploads: UploadService
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
        self.validate(user_id, request, model=model)
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
        self._log_submission(submission, result.replayed)
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
        self.validate(user_id, request, model=model)
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
        self._log_submission(submission, result.replayed)
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
        self.validate(user_id, request, model=model)
        source = await self.query.resolve_generated_image_source(
            source_image_key=request.source_image_key,
            user_id=user_id,
        )
        if source is None:
            raise NotFoundError("源图不存在或无权访问，请重新选择后再试")
        admission = await self._admit()
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
        self._log_submission(submission, result.replayed)
        return SubmissionReceipt(
            job_id=result.job_id,
            queue_state=admission.state,
            estimated_wait_seconds=admission.estimated_wait_seconds,
            replayed=result.replayed,
        )

    async def submit_background_replace(
        self,
        *,
        user_id: str,
        request: BackgroundReplaceRequest,
        idempotency_key: str,
        trace_id: str,
        request_id: str,
        model: ModelName = ModelName.GPT_IMAGE_2,
    ) -> SubmissionReceipt:
        self._require_idempotency_key(idempotency_key)
        source = None
        if request.source.kind == "upload":
            source_data = await self._load_owned_upload(
                user_id,
                request.source.upload_id,
            )
            ratio = closest_supported_ratio(source_data)
        else:
            source = await self.query.resolve_generated_image_source(
                source_image_key=request.source.image_key,
                user_id=user_id,
            )
            if source is None:
                raise NotFoundError("源图不存在或无权访问，请重新选择后再试")
            ratio = source.parent_ratio
        if request.background.kind == "reference":
            await self._load_owned_upload(
                user_id,
                request.background.upload_id,
            )

        admission = await self._admit()
        submission = self.planner.plan_background_replace(
            user_id=user_id,
            request=request,
            source=source,
            ratio=ratio,
            job_id=self.id_factory(),
            idempotency_key=idempotency_key,
            trace_id=trace_id,
            request_id=request_id,
            model=model,
        )
        result = await self.repository.submit(submission)
        self._log_submission(submission, result.replayed)
        return SubmissionReceipt(
            job_id=result.job_id,
            queue_state=admission.state,
            estimated_wait_seconds=admission.estimated_wait_seconds,
            replayed=result.replayed,
        )

    def validate(
        self,
        user_id: str,
        request: ListingGenerateRequest | CloneRequest | EditRequest,
        *,
        model: ModelName = ModelName.GPT_IMAGE_2,
    ) -> None:
        if isinstance(request, ListingGenerateRequest):
            if not 1 <= len(request.upload_ids) <= 3:
                raise ValueError(
                    f"请上传 1–3 张图片（当前 {len(request.upload_ids)} 张）"
                )
            self._require_owned_uploads(user_id, tuple(request.upload_ids))
            generation_size(model, request.ratio)
            build_listing_prompts(
                request.prompt,
                request.modifiers,
                self.planner.modifier_registry,
                self.planner.card_registry,
                self.planner.type_registry,
                category=request.category,
                n=request.n,
                plan=request.plan,
                overlay_texts=tuple(request.overlay_texts or ()),
            )
            return
        if isinstance(request, CloneRequest):
            if len(request.product_upload_ids) != 1:
                raise ValueError(
                    f"复刻需要 1 张产品图（当前 {len(request.product_upload_ids)} 张）"
                )
            if not 1 <= len(request.reference_upload_ids) <= 2:
                raise ValueError(
                    f"请上传 1–2 张爆款参考图（当前 {len(request.reference_upload_ids)} 张）"
                )
            self._require_owned_uploads(
                user_id,
                (
                    *request.product_upload_ids,
                    *request.reference_upload_ids,
                ),
            )
            generation_size(model, request.ratio)
            compose_clone_prompt(
                request.prompt,
                request.modifiers,
                self.planner.modifier_registry,
                category=request.category,
                card_registry=self.planner.card_registry,
                clone_registry=self.planner.clone_registry,
                clone_mode=request.clone_mode,
            )
            return
        self.planner.edit_registry.block(request.edit_mode)
        if request.edit_mode == "delta" and request.ratio is not None:
            raise ValueError(
                "微调会沿用原图比例，如需修改比例请改用「重做」"
            )
        if request.ratio is not None:
            generation_size(model, request.ratio)

    async def _admit(self) -> AdmissionResult:
        self.redis_health.require_available(now=self.clock())
        snapshot = await self.queue_snapshots.snapshot()
        result = self.admission.evaluate(
            queue_depth=snapshot.depth,
            rolling_item_seconds=snapshot.rolling_item_seconds,
            available_slots=snapshot.available_slots,
        )
        if result.state == "confirmation_required":
            raise AdmissionRejected(
                "generation wait exceeds 15 minutes and requires explicit confirmation"
            )
        return result

    @staticmethod
    def _require_idempotency_key(value: str) -> None:
        if not value or value.isspace() or len(value) > 128:
            raise ValueError("Idempotency-Key must contain 1 to 128 characters")

    @staticmethod
    def _require_owned_uploads(user_id: str, upload_keys: tuple[str, ...]) -> None:
        if any(not owns(key, user_id) for key in upload_keys):
            raise NotFoundError("有图片找不到或无权访问，请重新上传后再试")

    async def _load_owned_upload(self, user_id: str, upload_key: str) -> bytes:
        self._require_owned_uploads(user_id, (upload_key,))
        data, _content_type = await self.uploads.load(upload_key)
        return data

    @staticmethod
    def _log_submission(
        submission: JobSubmission, replayed: bool
    ) -> None:
        first = submission.items[0]
        logger.info(
            "generation_submission_accepted",
            extra={
                "request_id": submission.request_id,
                "trace_id": submission.trace_id,
                "job_id": submission.job.job_id,
                "item_id": first.item_id,
                "operation_id": first.operation_id,
                "status": "replayed" if replayed else "accepted",
            },
        )
