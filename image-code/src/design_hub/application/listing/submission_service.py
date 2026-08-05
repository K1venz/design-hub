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
from design_hub.domain.errors import DomainError, NotFoundError
from design_hub.domain.image_capabilities import image_model_capabilities
from design_hub.domain.tasking import RenderTier
from design_hub.ports.generation_work import (
    GenerationWorkRepository,
    JobSubmission,
)
from design_hub.ports.listing_query import (
    GeneratedImageSource,
    ListingHistoryQuery,
)
from design_hub.ports.model_config_repository import (
    ModelConfigRecord,
    ModelConfigRepository,
)
from design_hub.ports.model_resolution import ModelUnavailableError
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
    model_configs: ModelConfigRepository
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
        render_tier: RenderTier = RenderTier.STANDARD,
    ) -> SubmissionReceipt:
        config = await self._resolve_image_model(request, render_tier)
        self._require_idempotency_key(idempotency_key)
        self.validate(user_id, request, render_tier=render_tier)
        admission = await self._admit()
        submission = self.planner.plan_generate(
            user_id=user_id,
            request=request,
            job_id=self.id_factory(),
            idempotency_key=idempotency_key,
            trace_id=trace_id,
            request_id=request_id,
            model_id=config.name,
            unit_cost=config.unit_cost,
            render_tier=render_tier,
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
        render_tier: RenderTier = RenderTier.STANDARD,
    ) -> SubmissionReceipt:
        config = await self._resolve_image_model(request, render_tier)
        self._require_idempotency_key(idempotency_key)
        self.validate(user_id, request, render_tier=render_tier)
        admission = await self._admit()
        submission = self.planner.plan_clone(
            user_id=user_id,
            request=request,
            job_id=self.id_factory(),
            idempotency_key=idempotency_key,
            trace_id=trace_id,
            request_id=request_id,
            model_id=config.name,
            unit_cost=config.unit_cost,
            render_tier=render_tier,
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
        render_tier: RenderTier = RenderTier.STANDARD,
    ) -> SubmissionReceipt:
        config = await self._resolve_image_model(request, render_tier)
        self._require_idempotency_key(idempotency_key)
        self.validate(user_id, request, render_tier=render_tier)
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
            model_id=config.name,
            unit_cost=config.unit_cost,
            render_tier=render_tier,
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
        render_tier: RenderTier = RenderTier.STANDARD,
    ) -> SubmissionReceipt:
        config = await self._resolve_image_model(request, render_tier)
        self._require_idempotency_key(idempotency_key)
        source, ratio = await self._background_replace_context(
            user_id=user_id,
            request=request,
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
            model_id=config.name,
            unit_cost=config.unit_cost,
            render_tier=render_tier,
        )
        result = await self.repository.submit(submission)
        self._log_submission(submission, result.replayed)
        return SubmissionReceipt(
            job_id=result.job_id,
            queue_state=admission.state,
            estimated_wait_seconds=admission.estimated_wait_seconds,
            replayed=result.replayed,
        )

    async def validate_background_replace(
        self,
        *,
        user_id: str,
        request: BackgroundReplaceRequest,
    ) -> None:
        await self._resolve_image_model(request, RenderTier.STANDARD)
        await self._background_replace_context(
            user_id=user_id,
            request=request,
        )

    async def _background_replace_context(
        self,
        *,
        user_id: str,
        request: BackgroundReplaceRequest,
    ) -> tuple[GeneratedImageSource | None, str]:
        source: GeneratedImageSource | None = None
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
        return source, ratio

    def validate(
        self,
        user_id: str,
        request: ListingGenerateRequest | CloneRequest | EditRequest,
        *,
        render_tier: RenderTier = RenderTier.STANDARD,
    ) -> None:
        if isinstance(request, ListingGenerateRequest):
            if not 1 <= len(request.upload_ids) <= 3:
                raise ValueError(
                    f"请上传 1–3 张图片（当前 {len(request.upload_ids)} 张）"
                )
            self._require_owned_uploads(user_id, tuple(request.upload_ids))
            generation_size(request.image_model, render_tier, request.ratio)
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
            generation_size(request.image_model, render_tier, request.ratio)
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
            generation_size(request.image_model, render_tier, request.ratio)

    async def _resolve_image_model(
        self,
        request: (
            ListingGenerateRequest
            | CloneRequest
            | EditRequest
            | BackgroundReplaceRequest
        ),
        render_tier: RenderTier,
    ) -> ModelConfigRecord:
        try:
            config = await self.model_configs.require_available_image(
                request.image_model
            )
        except ModelUnavailableError:
            logger.warning(
                "generation_model_unavailable",
                extra={
                    "chain": "image_generation",
                    "action": "用户选择的模型不可用",
                    "model": request.image_model,
                    "status": "unavailable",
                },
            )
            raise
        capabilities = image_model_capabilities(config.name)
        capabilities.ratios(render_tier)
        count = (
            request.n
            if isinstance(request, ListingGenerateRequest)
            and request.n is not None
            else (
                sum(request.plan.values())
                if isinstance(request, ListingGenerateRequest)
                and request.plan is not None
                else 1
            )
        )
        if not 1 <= count <= capabilities.platform_max_count:
            raise DomainError(
                f"{config.display_name} 单次最多生成 "
                f"{capabilities.platform_max_count} 张图片"
            )
        return config

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
            "generation_task_created",
            extra={
                "chain": "image_generation",
                "action": "创建出图任务",
                "request_id": submission.request_id,
                "trace_id": submission.trace_id,
                "job_id": submission.job.job_id,
                "item_id": first.item_id,
                "operation_id": first.operation_id,
                "model": first.model,
                "status": "replayed" if replayed else "accepted",
            },
        )
