import asyncio
from collections.abc import Awaitable
from decimal import Decimal

import pytest

from design_hub.application.listing.listing_service import ListingGenerationService
from design_hub.application.listing.prompt_composer import (
    CategoryCardRegistry,
    CloneModeRegistry,
    EditModeRegistry,
    ImageTypeRegistry,
    PromptModifierRegistry,
)
from design_hub.application.registry import ProviderRegistry
from design_hub.domain.models import GeneratedImage, ListingResult, ReferenceImage
from design_hub.ports.model_calls import ModelCallContext


class _RecordingGuard:
    def __init__(self) -> None:
        self.reserved: list[Decimal] = []
        self.rolled_back: list[Decimal] = []

    async def precheck_and_reserve(self, user_id: str, estimate: Decimal) -> None:
        self.reserved.append(estimate)

    async def rollback(self, user_id: str, estimate: Decimal) -> None:
        self.rolled_back.append(estimate)

    async def reconcile(
        self, user_id: str, *, reserved: Decimal, actual: Decimal
    ) -> None:
        raise AssertionError("cancelled generation must not reconcile")


class _BlockingProvider:
    name = "gpt-image-2"
    unit_cost = Decimal("0.05")
    is_live = True
    reference_mode = "bytes"

    def __init__(self) -> None:
        self.started = asyncio.Event()

    async def generate(
        self,
        *,
        context: ModelCallContext,
        prompt: str,
        negative_prompt: str,
        reference_images: list[ReferenceImage],
        size: tuple[int, int],
        n: int,
        seed: int | None = None,
        quality: str | None = None,
    ) -> list[GeneratedImage]:
        del context
        self.started.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


def _service() -> tuple[ListingGenerationService, _BlockingProvider, _RecordingGuard]:
    provider = _BlockingProvider()
    registry = ProviderRegistry()
    registry.register(provider)  # type: ignore[arg-type]
    guard = _RecordingGuard()
    service = ListingGenerationService(
        registry=registry,
        guard=guard,  # type: ignore[arg-type]
        modifier_registry=PromptModifierRegistry(),
        card_registry=CategoryCardRegistry(),
        type_registry=ImageTypeRegistry(),
        clone_registry=CloneModeRegistry(),
        edit_registry=EditModeRegistry(),
    )
    return service, provider, guard


def _operation(
    service: ListingGenerationService, name: str
) -> Awaitable[ListingResult]:
    common = {
        "prompt": "极简商品主图",
        "modifiers": {},
        "ratio": "1:1",
        "user_id": "u1",
        "model": "gpt-image-2",
    }
    if name == "generate":
        return service.generate(
            **common,
            images=(b"product",),
            category=None,
            n=1,
        )
    if name == "clone":
        return service.clone(
            **common,
            product_image=b"product",
            reference_images=(b"reference",),
            category=None,
            clone_mode="参考风格",
        )
    if name == "edit":
        return service.edit(
            **common,
            source_image=b"source",
            anchor_images=(b"product",),
            edit_mode="delta",
        )
    raise AssertionError(name)


@pytest.mark.parametrize("operation", ["generate", "clone", "edit"])
def test_cancellation_after_precharge_rolls_back_before_reraising(
    operation: str,
) -> None:
    async def _impl() -> None:
        service, provider, guard = _service()
        task = asyncio.create_task(_operation(service, operation))
        await provider.started.wait()

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert guard.reserved == [Decimal("0.05")]
        assert guard.rolled_back == [Decimal("0.05")]

    asyncio.run(_impl())
