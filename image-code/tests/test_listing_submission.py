import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from design_hub.application.listing.prompt_composer import (
    CategoryCardRegistry,
    CloneModeRegistry,
    EditModeRegistry,
    ImageTypeRegistry,
    PromptModifierRegistry,
)
from design_hub.application.listing.requests import (
    BackgroundReplaceRequest,
    CloneRequest,
    EditRequest,
    ListingGenerateRequest,
)
from design_hub.application.listing.submission_service import (
    ListingSubmissionService,
    SubmissionReceipt,
)
from design_hub.application.listing.task_planner import ListingTaskPlanner
from design_hub.application.listing.upload_service import UploadService
from design_hub.application.tasking.health import (
    AdmissionRejected,
    QueueAdmissionController,
    QueueSnapshot,
    RedisHealthState,
    RedisUnavailable,
)
from design_hub.domain.enums import ModelType, ProviderType, Role, TaskEventType
from design_hub.domain.models import AuthUser, TaskEvent
from design_hub.domain.tasking import (
    OperationType,
    ReferenceSource,
    RenderTier,
)
from design_hub.interface.api.app import register_error_handlers
from design_hub.interface.api.deps import get_current_user, get_current_user_sse
from design_hub.interface.api.routes import listing
from design_hub.ports.events import ReplayableEvent, ReplayableEventStream
from design_hub.ports.generation_work import (
    IdempotencyConflict,
    JobSubmission,
    SubmitResult,
)
from design_hub.ports.listing_query import GeneratedImageSource, ListingHistoryQuery
from design_hub.ports.model_config_repository import ModelConfigRecord
from design_hub.ports.upload_store import UploadStore, upload_ns


def _planner() -> ListingTaskPlanner:
    return ListingTaskPlanner(
        modifier_registry=PromptModifierRegistry(),
        card_registry=CategoryCardRegistry(),
        type_registry=ImageTypeRegistry(),
        clone_registry=CloneModeRegistry(),
        edit_registry=EditModeRegistry(),
    )


@pytest.mark.parametrize(
    ("request_type", "payload"),
    [
        (
            ListingGenerateRequest,
            {
                "upload_ids": ["1/front.png"],
                "prompt": "red",
                "ratio": "1:1",
                "n": 1,
            },
        ),
        (
            CloneRequest,
            {
                "product_upload_ids": ["1/product.png"],
                "reference_upload_ids": ["1/reference.png"],
                "clone_mode": "参考风格",
                "ratio": "1:1",
            },
        ),
        (
            EditRequest,
            {
                "source_image_key": "source.png",
                "prompt": "red",
            },
        ),
        (
            BackgroundReplaceRequest,
            {
                "source": {
                    "kind": "upload",
                    "upload_id": "1/product.png",
                },
                "background": {
                    "kind": "description",
                    "description": "blue",
                },
            },
        ),
    ],
)
def test_every_listing_request_requires_nonblank_image_model(
    request_type: type,
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        request_type.model_validate(payload)
    with pytest.raises(ValidationError):
        request_type.model_validate({**payload, "image_model": "  "})


def test_generate_plan_freezes_each_image_prompt_and_reference_key() -> None:
    request = ListingGenerateRequest(
        image_model="gpt-image-2",
        upload_ids=["1/front.png", "1/side.png"],
        prompt="春节红色礼盒",
        ratio="1:1",
        plan={"白底": 1, "场景": 1, "卖点": 1},
        overlay_texts=["真材实料"],
        modifiers={"platform": "抖音电商"},
        category="FOOD",
    )

    submission = _planner().plan_generate(
        user_id="1",
        request=request,
        job_id="job-1",
        idempotency_key="idem-1",
        trace_id="trace-1",
        request_id="request-1",
        model_id="gpt-image-2",
        unit_cost=Decimal("0.05"),
    )

    assert submission.job.n == 3
    assert submission.job.upload_keys == ("1/front.png", "1/side.png")
    assert [item.image_type for item in submission.items] == ["白底", "场景", "卖点"]
    assert [item.sequence for item in submission.items] == [1, 2, 3]
    assert [item.seed for item in submission.items] == [0, 1, 2]
    assert all(item.operation_type is OperationType.GENERATE_IMAGE for item in submission.items)
    assert all(item.render_tier is RenderTier.STANDARD for item in submission.items)
    assert all(item.size == (1024, 1024) for item in submission.items)
    assert all(item.reserved_cost == Decimal("0.05") for item in submission.items)
    assert [item.quality for item in submission.items] == [None, None, "high"]
    assert "真材实料" in submission.items[2].final_prompt
    assert "真材实料" not in submission.items[0].final_prompt
    assert [
        (reference.source, reference.object_key, reference.role, reference.order)
        for reference in submission.items[0].references
    ] == [
        (ReferenceSource.UPLOAD, "1/front.png", "product", 0),
        (ReferenceSource.UPLOAD, "1/side.png", "product", 1),
    ]


def test_nano_banana_plan_uses_selected_model_two_k_dimensions() -> None:
    request = ListingGenerateRequest(
        image_model="nano-banana-2",
        upload_ids=["1/front.png"],
        prompt="product poster",
        ratio="4:5",
        n=1,
    )

    submission = _planner().plan_generate(
        user_id="1",
        request=request,
        job_id="job-nano",
        idempotency_key="idem-nano",
        trace_id="trace-nano",
        request_id="request-nano",
        model_id="nano-banana-2",
        unit_cost=Decimal("0.10"),
        render_tier=RenderTier.TWO_K,
    )

    assert submission.items[0].render_tier is RenderTier.TWO_K
    assert submission.items[0].ratio == "4:5"
    assert submission.items[0].size == (1856, 2304)


def test_request_fingerprint_is_stable_across_generated_ids_and_changes_with_input() -> None:
    planner = _planner()
    request = ListingGenerateRequest(
        image_model="gpt-image-2",
        upload_ids=["1/front.png"],
        prompt="red",
        ratio="1:1",
        n=1,
    )

    first = planner.plan_generate(
        user_id="1",
        request=request,
        job_id="job-1",
        idempotency_key="idem-1",
        trace_id="trace-1",
        request_id="request-1",
        model_id="gpt-image-2",
        unit_cost=Decimal("0.05"),
    )
    replay = planner.plan_generate(
        user_id="1",
        request=request,
        job_id="job-2",
        idempotency_key="idem-1",
        trace_id="trace-2",
        request_id="request-2",
        model_id="gpt-image-2",
        unit_cost=Decimal("0.05"),
    )
    changed = planner.plan_generate(
        user_id="1",
        request=request.model_copy(update={"prompt": "blue"}),
        job_id="job-3",
        idempotency_key="idem-1",
        trace_id="trace-3",
        request_id="request-3",
        model_id="gpt-image-2",
        unit_cost=Decimal("0.05"),
    )

    assert first.request_fingerprint == replay.request_fingerprint
    assert first.request_fingerprint != changed.request_fingerprint
    assert first.items[0].operation_id != replay.items[0].operation_id


def test_request_fingerprint_includes_render_tier_for_every_planner_operation() -> None:
    planner = _planner()
    generate = ListingGenerateRequest(
        image_model="gpt-image-2", upload_ids=["1/front.png"], prompt="red", ratio="16:9", n=1
    )
    clone = CloneRequest(
        image_model="gpt-image-2",
        product_upload_ids=["1/product.png"],
        reference_upload_ids=["1/reference.png"],
        clone_mode="完全复刻",
        ratio="16:9",
        prompt="red",
    )
    edit = EditRequest(
        image_model="gpt-image-2",
        source_image_key="source.png",
        prompt="red",
        edit_mode="full",
        ratio="16:9",
    )
    source = GeneratedImageSource(
        parent_job_id="parent-1",
        parent_ratio="16:9",
        parent_modifiers={},
        root_product_upload_keys=("1/product.png",),
    )
    background = BackgroundReplaceRequest.model_validate(
        {
            "image_model": "gpt-image-2",
            "source": {"kind": "upload", "upload_id": "1/product.png"},
            "background": {"kind": "description", "description": "blue"},
        }
    )

    plan_calls = (
        lambda render_tier: planner.plan_generate(
            user_id="1",
            request=generate,
            job_id="generate",
            idempotency_key="same",
            trace_id="trace",
            request_id="request",
            model_id="gpt-image-2",
            unit_cost=Decimal("0.05"),
            render_tier=render_tier,
        ),
        lambda render_tier: planner.plan_clone(
            user_id="1",
            request=clone,
            job_id="clone",
            idempotency_key="same",
            trace_id="trace",
            request_id="request",
            model_id="gpt-image-2",
            unit_cost=Decimal("0.05"),
            render_tier=render_tier,
        ),
        lambda render_tier: planner.plan_edit(
            user_id="1",
            request=edit,
            source=source,
            job_id="edit",
            idempotency_key="same",
            trace_id="trace",
            request_id="request",
            model_id="gpt-image-2",
            unit_cost=Decimal("0.05"),
            render_tier=render_tier,
        ),
        lambda render_tier: planner.plan_background_replace(
            user_id="1",
            request=background,
            source=None,
            ratio="16:9",
            job_id="background",
            idempotency_key="same",
            trace_id="trace",
            request_id="request",
            model_id="gpt-image-2",
            unit_cost=Decimal("0.05"),
            render_tier=render_tier,
        ),
    )
    for plan in plan_calls:
        standard = plan(RenderTier.STANDARD)
        four_k = plan(RenderTier.FOUR_K)
        assert standard.request_fingerprint != four_k.request_fingerprint


def test_clone_plan_preserves_product_then_reference_roles() -> None:
    request = CloneRequest(
        image_model="gpt-image-2",
        product_upload_ids=["1/product.png"],
        reference_upload_ids=["1/ref-a.png", "1/ref-b.png"],
        clone_mode="完全复刻",
        ratio="3:4",
        prompt="保留产品包装",
    )

    submission = _planner().plan_clone(
        user_id="1",
        request=request,
        job_id="clone-1",
        idempotency_key="idem-clone",
        trace_id="trace-1",
        request_id="request-1",
        model_id="gpt-image-2",
        unit_cost=Decimal("0.05"),
    )

    item = submission.items[0]
    assert item.operation_type is OperationType.CLONE_IMAGE
    assert item.size == (1152, 1536)
    assert submission.job.clone_mode == "完全复刻"
    assert submission.job.input_roles == ("product", "reference", "reference")
    assert [(reference.object_key, reference.role) for reference in item.references] == [
        ("1/product.png", "product"),
        ("1/ref-a.png", "reference"),
        ("1/ref-b.png", "reference"),
    ]


def test_edit_plan_freezes_source_then_root_anchors_and_effective_modifiers() -> None:
    request = EditRequest(
        image_model="gpt-image-2",
        source_image_key="source.png",
        prompt="背景改蓝色",
        edit_mode="full",
        modifiers={"language": "英文"},
        ratio="4:3",
    )
    source = GeneratedImageSource(
        parent_job_id="parent-1",
        parent_ratio="1:1",
        parent_modifiers={"platform": "抖音电商", "language": "中文"},
        root_product_upload_keys=("1/front.png", "1/side.png"),
    )

    submission = _planner().plan_edit(
        user_id="1",
        request=request,
        source=source,
        job_id="edit-1",
        idempotency_key="idem-edit",
        trace_id="trace-1",
        request_id="request-1",
        model_id="gpt-image-2",
        unit_cost=Decimal("0.05"),
    )

    item = submission.items[0]
    assert item.operation_type is OperationType.EDIT_IMAGE
    assert submission.job.parent_job_id == "parent-1"
    assert submission.job.source_image_key == "source.png"
    assert submission.job.modifiers == {"platform": "抖音电商", "language": "英文"}
    references = [
        (reference.source, reference.object_key, reference.role) for reference in item.references
    ]
    assert references == [
        (ReferenceSource.GENERATED, "source.png", "source"),
        (ReferenceSource.UPLOAD, "1/front.png", "product"),
        (ReferenceSource.UPLOAD, "1/side.png", "product"),
    ]


class _SubmissionService:
    def __init__(self) -> None:
        self.receipt = SubmissionReceipt(
            job_id="job-accepted",
            queue_state="normal",
            estimated_wait_seconds=12,
            replayed=False,
        )
        self.error: Exception | None = None
        self.keys: list[str] = []

    async def submit_generate(
        self,
        *,
        user_id: str,
        request: ListingGenerateRequest,
        idempotency_key: str,
        trace_id: str,
        request_id: str,
        model: str = "gpt-image-2",
    ) -> SubmissionReceipt:
        self.keys.append(idempotency_key)
        if self.error is not None:
            raise self.error
        return self.receipt

    async def submit_background_replace(
        self,
        *,
        user_id: str,
        request: BackgroundReplaceRequest,
        idempotency_key: str,
        trace_id: str,
        request_id: str,
        model: str = "gpt-image-2",
    ) -> SubmissionReceipt:
        self.keys.append(idempotency_key)
        if self.error is not None:
            raise self.error
        return self.receipt


class _OwnerQuery(ListingHistoryQuery):
    def __init__(self, owned: bool) -> None:
        self.owned = owned

    async def list_jobs(
        self,
        *,
        user_id: str,
        limit: int,
        offset: int,
        q: str | None = None,
    ) -> list[object]:
        return []

    async def get_job(self, *, job_id: str, user_id: str) -> object | None:
        return object() if self.owned else None

    async def resolve_generated_image_source(
        self, *, source_image_key: str, user_id: str
    ) -> GeneratedImageSource | None:
        return None


class _UnusedUploads(UploadStore):
    async def save(self, data: bytes, *, content_type: str, user_id: str) -> str:
        raise AssertionError("save is not used")

    async def load(self, upload_id: str) -> tuple[bytes, str]:
        raise AssertionError("load is not used")


class _ReplayStream(ReplayableEventStream):
    def __init__(self) -> None:
        self.reads: list[tuple[str, str]] = []

    async def read(
        self, *, job_id: str, after_id: str, block_ms: int
    ) -> tuple[ReplayableEvent, ...]:
        self.reads.append((job_id, after_id))
        return (
            ReplayableEvent(
                redis_id="15-0",
                event=TaskEvent(
                    job_id=job_id,
                    type=TaskEventType.TASK_COMPLETED,
                    data={"status": "完成"},
                ),
            ),
        )


def _http_client(
    *,
    owned: bool = True,
) -> tuple[TestClient, _SubmissionService, _ReplayStream]:
    app = FastAPI()
    app.include_router(listing.router)
    register_error_handlers(app)
    service = _SubmissionService()
    stream = _ReplayStream()
    app.state.listing_submission = service
    app.state.listing_query = _OwnerQuery(owned)
    app.state.event_stream = stream

    async def user() -> AuthUser:
        return AuthUser(user_id="1", name="User", role=Role.DESIGNER)

    app.dependency_overrides[get_current_user] = user
    app.dependency_overrides[get_current_user_sse] = user
    return TestClient(app), service, stream


def _generate_payload() -> dict[str, object]:
    return {
        "image_model": "gpt-image-2",
        "upload_ids": [f"{upload_ns('1')}/product.png"],
        "prompt": "red package",
        "ratio": "1:1",
        "n": 1,
    }


def test_listing_submission_requires_idempotency_key_and_returns_202_metadata() -> None:
    client, service, _stream = _http_client()

    missing = client.post("/listing/generate", json=_generate_payload())
    accepted = client.post(
        "/listing/generate",
        headers={"Idempotency-Key": "request-1"},
        json=_generate_payload(),
    )

    assert missing.status_code == 400
    assert accepted.status_code == 202
    assert accepted.json() == {
        "job_id": "job-accepted",
        "queue_state": "normal",
        "estimated_wait_seconds": 12,
    }
    assert service.keys == ["request-1"]


def test_background_replace_route_uses_shared_submission_contract() -> None:
    client, service, _stream = _http_client()

    response = client.post(
        "/listing/background-replace",
        headers={"Idempotency-Key": "background-1"},
        json={
            "image_model": "gpt-image-2",
            "source": {
                "kind": "upload",
                "upload_id": f"{upload_ns('1')}/product.png",
            },
            "background": {
                "kind": "description",
                "description": "明亮咖啡店",
            },
        },
    )

    assert response.status_code == 202
    assert response.json()["job_id"] == "job-accepted"
    assert service.keys == ["background-1"]


def test_listing_submission_maps_conflict_and_capacity_failures() -> None:
    client, service, _stream = _http_client()
    cases = [
        (IdempotencyConflict("changed request"), 409, "idempotency_conflict"),
        (RedisUnavailable("redis down"), 503, "generation_unavailable"),
        (AdmissionRejected("queue full"), 503, "generation_unavailable"),
    ]
    for error, expected_status, expected_code in cases:
        service.error = error
        response = client.post(
            "/listing/generate",
            headers={"Idempotency-Key": "request-1"},
            json=_generate_payload(),
        )
        assert response.status_code == expected_status
        assert response.json()["error"] == expected_code


def test_listing_sse_replays_after_last_event_id_and_emits_sse_id() -> None:
    client, _service, stream = _http_client()

    response = client.get(
        "/listing/job-1/events",
        headers={"Last-Event-ID": "14-0"},
    )

    assert response.status_code == 200
    assert response.text.startswith("id: 15-0\nevent: task_completed\ndata: ")
    assert stream.reads == [("job-1", "14-0")]


def test_listing_sse_checks_owner_before_reading_stream() -> None:
    client, _service, stream = _http_client(owned=False)

    response = client.get("/listing/job-1/events")

    assert response.status_code == 404
    assert stream.reads == []


class _SubmissionRepository:
    def __init__(self) -> None:
        self.saved: dict[tuple[str, str], tuple[str, str]] = {}
        self.calls = 0

    async def submit(self, submission: JobSubmission) -> SubmitResult:
        self.calls += 1
        key = (submission.job.user_id, submission.idempotency_key)
        existing = self.saved.get(key)
        if existing is not None:
            job_id, fingerprint = existing
            if fingerprint != submission.request_fingerprint:
                raise IdempotencyConflict("changed request")
            return SubmitResult(job_id=job_id, replayed=True)
        self.saved[key] = (
            submission.job.job_id,
            submission.request_fingerprint,
        )
        return SubmitResult(job_id=submission.job.job_id, replayed=False)


class _Snapshots:
    def __init__(self, depth: int = 0) -> None:
        self.depth = depth

    async def snapshot(self) -> QueueSnapshot:
        return QueueSnapshot(
            depth=self.depth,
            rolling_item_seconds=60,
            available_slots=3,
        )


class _ModelConfigs:
    def __init__(self, name: str = "gpt-image-2") -> None:
        self.name = name

    async def require_available_image(self, name: str) -> ModelConfigRecord:
        assert name == self.name
        return ModelConfigRecord(
            name=name,
            display_name=name,
            model_type=ModelType.IMAGE,
            provider_type=(
                ProviderType.DASHSCOPE_WAN_IMAGE
                if name == "wan2.7-image-pro"
                else ProviderType.OPENAI_COMPAT_IMAGE
            ),
            base_url="https://example.invalid",
            model="upstream",
            credentials_ciphertext={"standard_api_keys": ["encrypted"]},
            unit_cost=Decimal("0.05"),
            enabled=True,
            revision=1,
            verified_at=datetime.now(UTC),
            verified_fingerprint="verified",
            extra={},
        )


def _submission_service(
    repository: _SubmissionRepository,
    health: RedisHealthState,
    snapshots: _Snapshots,
    *,
    model_name: str = "gpt-image-2",
) -> ListingSubmissionService:
    ids = iter(("job-first", "job-replay", "job-tier-changed", "job-changed"))
    return ListingSubmissionService(
        planner=_planner(),
        repository=repository,  # type: ignore[arg-type]
        query=_OwnerQuery(True),
        uploads=UploadService(_UnusedUploads()),
        redis_health=health,
        queue_snapshots=snapshots,
        admission=QueueAdmissionController(
            soft_wait_seconds=300,
            confirm_wait_seconds=900,
            hard_depth=2000,
        ),
        model_configs=_ModelConfigs(model_name),  # type: ignore[arg-type]
        clock=lambda: 10,
        id_factory=lambda: next(ids),
    )


def test_submission_service_replays_same_key_and_rejects_changed_request() -> None:
    async def run() -> None:
        repository = _SubmissionRepository()
        health = RedisHealthState(stale_after_seconds=6)
        health.mark_healthy(now=10)
        service = _submission_service(repository, health, _Snapshots())
        request = ListingGenerateRequest(**(_generate_payload() | {"ratio": "16:9"}))

        first = await service.submit_generate(
            user_id="1",
            request=request,
            idempotency_key="same-key",
            trace_id="trace-1",
            request_id="request-1",
        )
        replay = await service.submit_generate(
            user_id="1",
            request=request,
            idempotency_key="same-key",
            trace_id="trace-2",
            request_id="request-2",
        )

        assert first.job_id == replay.job_id == "job-first"
        assert first.replayed is False
        assert replay.replayed is True

        with pytest.raises(IdempotencyConflict):
            await service.submit_generate(
                user_id="1",
                request=request,
                idempotency_key="same-key",
                trace_id="trace-3",
                request_id="request-3",
                render_tier=RenderTier.FOUR_K,
            )

        with pytest.raises(IdempotencyConflict):
            await service.submit_generate(
                user_id="1",
                request=request.model_copy(update={"prompt": "blue package"}),
                idempotency_key="same-key",
                trace_id="trace-3",
                request_id="request-3",
            )

    asyncio.run(run())


def test_wan_4k_accepts_reference_free_text_to_image() -> None:
    async def run() -> None:
        repository = _SubmissionRepository()
        health = RedisHealthState(stale_after_seconds=6)
        health.mark_healthy(now=10)
        service = _submission_service(
            repository,
            health,
            _Snapshots(),
            model_name="wan2.7-image-pro",
        )
        request = ListingGenerateRequest(
            image_model="wan2.7-image-pro",
            upload_ids=[],
            prompt="minimal product poster",
            ratio="1:4",
            n=1,
        )

        receipt = await service.submit_generate(
            user_id="1",
            request=request,
            idempotency_key="wan-text-only",
            trace_id="trace-wan-text-only",
            request_id="request-wan-text-only",
            render_tier=RenderTier.FOUR_K,
        )

        assert receipt.job_id == "job-first"
        assert repository.calls == 1

    asyncio.run(run())


def test_wan_4k_rejects_every_reference_operation_before_enqueue() -> None:
    async def run() -> None:
        repository = _SubmissionRepository()
        health = RedisHealthState(stale_after_seconds=6)
        health.mark_healthy(now=10)
        service = _submission_service(
            repository,
            health,
            _Snapshots(),
            model_name="wan2.7-image-pro",
        )
        generate = ListingGenerateRequest(
            image_model="wan2.7-image-pro",
            upload_ids=["1/product.png"],
            prompt="poster",
            ratio="1:1",
            n=1,
        )
        clone = CloneRequest(
            image_model="wan2.7-image-pro",
            product_upload_ids=["1/product.png"],
            reference_upload_ids=["1/reference.png"],
            clone_mode="参考风格",
            ratio="1:1",
        )
        edit = EditRequest(
            image_model="wan2.7-image-pro",
            source_image_key="generated/source.png",
            prompt="make it blue",
        )
        background = BackgroundReplaceRequest.model_validate(
            {
                "image_model": "wan2.7-image-pro",
                "source": {"kind": "upload", "upload_id": "1/product.png"},
                "background": {"kind": "description", "description": "blue"},
            }
        )

        calls = (
            lambda: service.submit_generate(
                user_id="1",
                request=generate,
                idempotency_key="wan-generate",
                trace_id="trace-wan-generate",
                request_id="request-wan-generate",
                render_tier=RenderTier.FOUR_K,
            ),
            lambda: service.submit_clone(
                user_id="1",
                request=clone,
                idempotency_key="wan-clone",
                trace_id="trace-wan-clone",
                request_id="request-wan-clone",
                render_tier=RenderTier.FOUR_K,
            ),
            lambda: service.submit_edit(
                user_id="1",
                request=edit,
                idempotency_key="wan-edit",
                trace_id="trace-wan-edit",
                request_id="request-wan-edit",
                render_tier=RenderTier.FOUR_K,
            ),
            lambda: service.submit_background_replace(
                user_id="1",
                request=background,
                idempotency_key="wan-background",
                trace_id="trace-wan-background",
                request_id="request-wan-background",
                render_tier=RenderTier.FOUR_K,
            ),
        )
        for call in calls:
            with pytest.raises(
                ValueError,
                match="does not support references at 4k",
            ):
                await call()

        assert repository.calls == 0

    asyncio.run(run())


def test_submission_service_rejects_before_database_write_when_unavailable() -> None:
    async def run() -> None:
        repository = _SubmissionRepository()
        unhealthy = RedisHealthState(stale_after_seconds=6)
        service = _submission_service(repository, unhealthy, _Snapshots())
        request = ListingGenerateRequest(**_generate_payload())

        with pytest.raises(RedisUnavailable):
            await service.submit_generate(
                user_id="1",
                request=request,
                idempotency_key="request-1",
                trace_id="trace-1",
                request_id="request-1",
            )
        assert repository.calls == 0

        healthy = RedisHealthState(stale_after_seconds=6)
        healthy.mark_healthy(now=10)
        full = _submission_service(repository, healthy, _Snapshots(depth=2000))
        with pytest.raises(AdmissionRejected):
            await full.submit_generate(
                user_id="1",
                request=request,
                idempotency_key="request-2",
                trace_id="trace-2",
                request_id="request-2",
            )
        assert repository.calls == 0

        confirmation_required = _submission_service(
            repository,
            healthy,
            _Snapshots(depth=46),
        )
        with pytest.raises(AdmissionRejected, match="explicit confirmation"):
            await confirmation_required.submit_generate(
                user_id="1",
                request=request,
                idempotency_key="request-3",
                trace_id="trace-3",
                request_id="request-3",
            )
        assert repository.calls == 0

    asyncio.run(run())
