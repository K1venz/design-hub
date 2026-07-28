import asyncio
from decimal import Decimal

from design_hub.application.cost.budget import BudgetPolicy
from design_hub.application.cost.guard import CostGuard
from design_hub.application.listing.listing_service import ListingGenerationService
from design_hub.application.listing.prompt_composer import (
    CategoryCardRegistry,
    CloneModeRegistry,
    EditModeRegistry,
    ImageTypeRegistry,
    PromptModifierRegistry,
)
from design_hub.application.listing.requests import (
    CloneRequest,
    EditRequest,
    ListingGenerateRequest,
)
from design_hub.application.listing.task_planner import ListingTaskPlanner
from design_hub.application.registry import ProviderRegistry
from design_hub.composition import build_mock_registry
from design_hub.domain.enums import ModelName
from design_hub.domain.models import BudgetSnapshot, GeneratedImage, ReferenceImage
from design_hub.domain.tasking import (
    OperationType,
    ReferenceSource,
    RenderTier,
)
from design_hub.ports.ledger import LedgerRepository
from design_hub.ports.listing_query import EditSource
from design_hub.ports.model_provider import AbstractModelProvider


class _NoopLedger(LedgerRepository):
    async def snapshot(self, user_id: str) -> BudgetSnapshot:
        return BudgetSnapshot(Decimal("0"), Decimal("100"), Decimal("0"), Decimal("1000"))

    async def reserve(
        self, user_id: str, amount: Decimal, *, operation_id: str
    ) -> None:
        raise AssertionError("execute_item must not reserve cost")

    async def rollback(
        self, user_id: str, amount: Decimal, *, operation_id: str
    ) -> None:
        raise AssertionError("execute_item must not refund cost")


class _CapturingProvider(AbstractModelProvider):
    name = ModelName.GPT_IMAGE_2
    unit_cost = Decimal("0.05")

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def generate(
        self,
        *,
        prompt: str,
        negative_prompt: str,
        reference_images: list[ReferenceImage],
        size: tuple[int, int],
        n: int,
        seed: int | None = None,
        quality: str | None = None,
    ) -> list[GeneratedImage]:
        self.calls.append(
            {
                "prompt": prompt,
                "reference_images": reference_images,
                "size": size,
                "n": n,
                "seed": seed,
                "quality": quality,
            }
        )
        return [
            GeneratedImage(
                image_key="result.png",
                url="mock://result.png",
                seed=seed or 0,
                latency_ms=10,
                cost=self.unit_cost,
            )
        ]


def _planner() -> ListingTaskPlanner:
    return ListingTaskPlanner(
        registry=build_mock_registry(),
        modifier_registry=PromptModifierRegistry(),
        card_registry=CategoryCardRegistry(),
        type_registry=ImageTypeRegistry(),
        clone_registry=CloneModeRegistry(),
        edit_registry=EditModeRegistry(),
    )


def test_generate_plan_freezes_each_image_prompt_and_reference_key() -> None:
    request = ListingGenerateRequest(
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
        model=ModelName.GPT_IMAGE_2,
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


def test_request_fingerprint_is_stable_across_generated_ids_and_changes_with_input() -> None:
    planner = _planner()
    request = ListingGenerateRequest(
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
        model=ModelName.GPT_IMAGE_2,
    )
    replay = planner.plan_generate(
        user_id="1",
        request=request,
        job_id="job-2",
        idempotency_key="idem-1",
        trace_id="trace-2",
        request_id="request-2",
        model=ModelName.GPT_IMAGE_2,
    )
    changed = planner.plan_generate(
        user_id="1",
        request=request.model_copy(update={"prompt": "blue"}),
        job_id="job-3",
        idempotency_key="idem-1",
        trace_id="trace-3",
        request_id="request-3",
        model=ModelName.GPT_IMAGE_2,
    )

    assert first.request_fingerprint == replay.request_fingerprint
    assert first.request_fingerprint != changed.request_fingerprint
    assert first.items[0].operation_id != replay.items[0].operation_id


def test_clone_plan_preserves_product_then_reference_roles() -> None:
    request = CloneRequest(
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
        model=ModelName.GPT_IMAGE_2,
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
        source_image_key="source.png",
        prompt="背景改蓝色",
        edit_mode="full",
        modifiers={"language": "英文"},
        ratio="4:3",
    )
    source = EditSource(
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
        model=ModelName.GPT_IMAGE_2,
    )

    item = submission.items[0]
    assert item.operation_type is OperationType.EDIT_IMAGE
    assert submission.job.parent_job_id == "parent-1"
    assert submission.job.source_image_key == "source.png"
    assert submission.job.modifiers == {"platform": "抖音电商", "language": "英文"}
    references = [
        (reference.source, reference.object_key, reference.role)
        for reference in item.references
    ]
    assert references == [
        (ReferenceSource.GENERATED, "source.png", "source"),
        (ReferenceSource.UPLOAD, "1/front.png", "product"),
        (ReferenceSource.UPLOAD, "1/side.png", "product"),
    ]


def test_execute_item_calls_provider_once_without_cost_side_effects() -> None:
    async def run() -> None:
        provider = _CapturingProvider()
        registry = ProviderRegistry()
        registry.register(provider)
        planner = ListingTaskPlanner(
            registry=registry,
            modifier_registry=PromptModifierRegistry(),
            card_registry=CategoryCardRegistry(),
            type_registry=ImageTypeRegistry(),
            clone_registry=CloneModeRegistry(),
            edit_registry=EditModeRegistry(),
        )
        request = ListingGenerateRequest(
            upload_ids=["1/front.png"],
            prompt="red",
            ratio="1:1",
            n=1,
        )
        item = planner.plan_generate(
            user_id="1",
            request=request,
            job_id="job-1",
            idempotency_key="idem-1",
            trace_id="trace-1",
            request_id="request-1",
            model=ModelName.GPT_IMAGE_2,
        ).items[0]
        service = ListingGenerationService(
            registry=registry,
            guard=CostGuard(ledger=_NoopLedger(), policy=BudgetPolicy()),
            modifier_registry=PromptModifierRegistry(),
            card_registry=CategoryCardRegistry(),
            type_registry=ImageTypeRegistry(),
            clone_registry=CloneModeRegistry(),
            edit_registry=EditModeRegistry(),
        )
        references = [ReferenceImage(data=b"product")]

        result = await service.execute_item(item, references)

        assert result.image_key == "result.png"
        assert provider.calls == [
            {
                "prompt": item.final_prompt,
                "reference_images": references,
                "size": (1024, 1024),
                "n": 1,
                "seed": 0,
                "quality": None,
            }
        ]

    asyncio.run(run())
