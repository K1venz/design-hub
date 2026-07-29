import asyncio
from io import BytesIO

import pytest
from PIL import Image
from pydantic import ValidationError

from design_hub.application.listing.background_replacement import (
    closest_supported_ratio,
    compose_background_replace_prompt,
)
from design_hub.application.listing.prompt_composer import (
    CategoryCardRegistry,
    CloneModeRegistry,
    EditModeRegistry,
    ImageTypeRegistry,
    PromptModifierRegistry,
)
from design_hub.application.listing.requests import BackgroundReplaceRequest
from design_hub.application.listing.submission_service import (
    ListingSubmissionService,
)
from design_hub.application.listing.task_planner import ListingTaskPlanner
from design_hub.application.listing.upload_service import UploadService
from design_hub.application.tasking.health import (
    QueueAdmissionController,
    QueueSnapshot,
    RedisHealthState,
)
from design_hub.composition import build_mock_registry
from design_hub.domain.enums import ModelName
from design_hub.domain.errors import NotFoundError
from design_hub.domain.tasking import OperationType, ReferenceSource
from design_hub.ports.generation_work import (
    JobSubmission,
    SubmitResult,
)
from design_hub.ports.listing_query import (
    GeneratedImageSource,
    ListingHistoryQuery,
)
from design_hub.ports.upload_store import UploadStore, upload_ns


def _planner() -> ListingTaskPlanner:
    return ListingTaskPlanner(
        registry=build_mock_registry(),
        modifier_registry=PromptModifierRegistry(),
        card_registry=CategoryCardRegistry(),
        type_registry=ImageTypeRegistry(),
        clone_registry=CloneModeRegistry(),
        edit_registry=EditModeRegistry(),
    )


def _png(width: int, height: int) -> bytes:
    output = BytesIO()
    Image.new("RGB", (width, height), "white").save(output, format="PNG")
    return output.getvalue()


def test_background_replace_request_forbids_unknown_and_invalid_variant_fields() -> None:
    valid = {
        "source": {"kind": "upload", "upload_id": "abc/product.png"},
        "background": {
            "kind": "reference",
            "upload_id": "abc/background.png",
            "instruction": "  商品放在桌面中央  ",
        },
    }

    request = BackgroundReplaceRequest.model_validate(valid)

    assert request.background.kind == "reference"
    assert request.background.instruction == "商品放在桌面中央"
    with pytest.raises(ValidationError):
        BackgroundReplaceRequest.model_validate({**valid, "quality": "high"})
    with pytest.raises(ValidationError):
        BackgroundReplaceRequest.model_validate(
            {
                "source": {
                    "kind": "upload",
                    "upload_id": "abc/product.png",
                    "image_key": "generated.png",
                },
                "background": {"kind": "description", "description": "咖啡店"},
            }
        )
    with pytest.raises(ValidationError):
        BackgroundReplaceRequest.model_validate(
            {
                "source": {"kind": "generated", "image_key": "generated.png"},
                "background": {"kind": "description", "description": "  "},
            }
        )


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        ((1024, 1024), "1:1"),
        ((900, 1200), "3:4"),
        ((1200, 900), "4:3"),
        ((900, 1600), "9:16"),
        ((1600, 900), "16:9"),
    ],
)
def test_closest_supported_ratio_reads_real_image_dimensions(
    size: tuple[int, int],
    expected: str,
) -> None:
    assert closest_supported_ratio(_png(*size)) == expected


def test_closest_supported_ratio_rejects_damaged_image() -> None:
    with pytest.raises(ValueError, match="图片损坏"):
        closest_supported_ratio(b"not-an-image")


def test_background_prompt_keeps_user_text_inside_fixed_fidelity_rules() -> None:
    request = BackgroundReplaceRequest.model_validate(
        {
            "source": {"kind": "upload", "upload_id": "abc/product.png"},
            "background": {
                "kind": "description",
                "description": "明亮的现代咖啡店，暖色自然光",
            },
        }
    )

    prompt = compose_background_replace_prompt(request.background)

    assert "只替换图片 1 的背景" in prompt
    assert "明亮的现代咖啡店，暖色自然光" in prompt
    assert prompt.index("明亮的现代咖啡店") < prompt.index("必须保持不变")
    assert "修改品牌、文字和包装信息" in prompt


def test_plan_background_replace_upload_source_uses_only_product_reference() -> None:
    request = BackgroundReplaceRequest.model_validate(
        {
            "source": {"kind": "upload", "upload_id": "abc/product.png"},
            "background": {
                "kind": "description",
                "description": "明亮的现代咖啡店",
            },
        }
    )

    submission = _planner().plan_background_replace(
        user_id="user-1",
        request=request,
        source=None,
        ratio="3:4",
        job_id="background-1",
        idempotency_key="idem-1",
        trace_id="trace-1",
        request_id="request-1",
        model=ModelName.GPT_IMAGE_2,
    )

    item = submission.items[0]
    assert item.operation_type is OperationType.REPLACE_BACKGROUND
    assert item.ratio == "3:4"
    assert item.size == (1152, 1536)
    assert [
        (reference.source, reference.object_key, reference.role, reference.order)
        for reference in item.references
    ] == [
        (ReferenceSource.UPLOAD, "abc/product.png", "product", 0),
    ]
    assert submission.job.upload_keys == ("abc/product.png",)
    assert submission.job.input_roles == ("product",)
    assert submission.job.parent_job_id is None


def test_plan_background_replace_generated_source_preserves_parent_and_reference_order() -> None:
    request = BackgroundReplaceRequest.model_validate(
        {
            "source": {"kind": "generated", "image_key": "generated.png"},
            "background": {
                "kind": "reference",
                "upload_id": "abc/background.png",
                "instruction": "商品放在桌面中央",
            },
        }
    )
    source = GeneratedImageSource(
        parent_job_id="parent-1",
        parent_ratio="16:9",
        parent_modifiers={},
        root_product_upload_keys=("abc/root-product.png",),
    )

    submission = _planner().plan_background_replace(
        user_id="user-1",
        request=request,
        source=source,
        ratio="16:9",
        job_id="background-2",
        idempotency_key="idem-2",
        trace_id="trace-2",
        request_id="request-2",
        model=ModelName.GPT_IMAGE_2,
    )

    item = submission.items[0]
    assert [
        (reference.source, reference.object_key, reference.role, reference.order)
        for reference in item.references
    ] == [
        (ReferenceSource.GENERATED, "generated.png", "source", 0),
        (ReferenceSource.UPLOAD, "abc/background.png", "background", 1),
    ]
    assert submission.job.upload_keys == ("abc/background.png",)
    assert submission.job.input_roles == ("background",)
    assert submission.job.parent_job_id == "parent-1"
    assert submission.job.source_image_key == "generated.png"


class _MemoryUploads(UploadStore):
    def __init__(self, images: dict[str, bytes]) -> None:
        self.images = images
        self.loaded: list[str] = []

    async def save(self, data: bytes, *, content_type: str, user_id: str) -> str:
        raise AssertionError("save is not used")

    async def load(self, upload_id: str) -> tuple[bytes, str]:
        self.loaded.append(upload_id)
        try:
            return self.images[upload_id], "image/png"
        except KeyError:
            raise NotFoundError(f"上传图不存在：{upload_id}") from None


class _Query(ListingHistoryQuery):
    def __init__(self, source: GeneratedImageSource | None = None) -> None:
        self.source = source

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
        return None

    async def resolve_generated_image_source(
        self,
        *,
        source_image_key: str,
        user_id: str,
    ) -> GeneratedImageSource | None:
        return self.source


class _Repository:
    def __init__(self) -> None:
        self.submission: JobSubmission | None = None

    async def submit(self, submission: JobSubmission) -> SubmitResult:
        self.submission = submission
        return SubmitResult(job_id=submission.job.job_id, replayed=False)


class _Snapshots:
    async def snapshot(self) -> QueueSnapshot:
        return QueueSnapshot(
            depth=0,
            rolling_item_seconds=60,
            available_slots=3,
        )


def _service(
    *,
    uploads: _MemoryUploads,
    query: _Query | None = None,
) -> tuple[ListingSubmissionService, _Repository]:
    repository = _Repository()
    health = RedisHealthState(stale_after_seconds=6)
    health.mark_healthy(now=10)
    service = ListingSubmissionService(
        planner=_planner(),
        repository=repository,  # type: ignore[arg-type]
        query=query or _Query(),
        uploads=UploadService(uploads),
        redis_health=health,
        queue_snapshots=_Snapshots(),
        admission=QueueAdmissionController(
            soft_wait_seconds=300,
            confirm_wait_seconds=900,
            hard_depth=2000,
        ),
        clock=lambda: 10,
        id_factory=lambda: "background-job",
    )
    return service, repository


def test_submit_background_replace_loads_owned_images_before_enqueue() -> None:
    async def run() -> None:
        namespace = upload_ns("user-1")
        product = f"{namespace}/product.png"
        background = f"{namespace}/background.png"
        uploads = _MemoryUploads(
            {
                product: _png(900, 1200),
                background: _png(1200, 900),
            }
        )
        service, repository = _service(uploads=uploads)
        request = BackgroundReplaceRequest.model_validate(
            {
                "source": {"kind": "upload", "upload_id": product},
                "background": {
                    "kind": "reference",
                    "upload_id": background,
                },
            }
        )

        receipt = await service.submit_background_replace(
            user_id="user-1",
            request=request,
            idempotency_key="idem-background",
            trace_id="trace-1",
            request_id="request-1",
        )

        assert receipt.job_id == "background-job"
        assert uploads.loaded == [product, background]
        assert repository.submission is not None
        assert repository.submission.job.ratio == "3:4"

    asyncio.run(run())


def test_submit_background_replace_hides_foreign_upload_existence() -> None:
    async def run() -> None:
        foreign = f"{upload_ns('other-user')}/product.png"
        uploads = _MemoryUploads({foreign: _png(1024, 1024)})
        service, repository = _service(uploads=uploads)
        request = BackgroundReplaceRequest.model_validate(
            {
                "source": {"kind": "upload", "upload_id": foreign},
                "background": {
                    "kind": "description",
                    "description": "咖啡店",
                },
            }
        )

        with pytest.raises(NotFoundError):
            await service.submit_background_replace(
                user_id="user-1",
                request=request,
                idempotency_key="idem-background",
                trace_id="trace-1",
                request_id="request-1",
            )

        assert uploads.loaded == []
        assert repository.submission is None

    asyncio.run(run())
