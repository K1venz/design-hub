from dataclasses import dataclass
from decimal import Decimal

from design_hub.application.cost.guard import CostGuard
from design_hub.application.listing.prompt_composer import (
    PromptModifierRegistry,
    compose_prompt,
)
from design_hub.application.listing.sizing import ratio_to_size
from design_hub.application.registry import ProviderRegistry
from design_hub.domain.enums import ModelName
from design_hub.domain.models import ListingResult

_MAX_IMAGES = 3
_MAX_N = 7


@dataclass
class ListingGenerationService:
    """listing 轻量出图用例：组装 prompt → 守门预扣 → gpt-image-2 直 edit → 回正。

    不走 PromptOrchestrator/ModelRouter（纯 prompt 直出，live edit 仅 gpt-image-2）。
    """

    registry: ProviderRegistry
    guard: CostGuard
    modifier_registry: PromptModifierRegistry

    async def generate(
        self,
        *,
        prompt: str,
        modifiers: dict[str, str],
        images: tuple[bytes, ...],
        ratio: str,
        n: int,
        user_id: str,
    ) -> ListingResult:
        if not 1 <= len(images) <= _MAX_IMAGES:
            raise ValueError(f"参考图数量需为 1..{_MAX_IMAGES}，实际 {len(images)}")
        if not 1 <= n <= _MAX_N:
            raise ValueError(f"张数需为 1..{_MAX_N}，实际 {n}")
        final_prompt = compose_prompt(prompt, modifiers, self.modifier_registry)
        size = ratio_to_size(ratio)
        provider = self.registry.get(ModelName.GPT_IMAGE_2)
        estimate = provider.unit_cost * n
        await self.guard.precheck_and_reserve(user_id, estimate)
        try:
            generated = await provider.generate(
                prompt=final_prompt,
                negative_prompt="",
                reference_images=list(images),
                size=size,
                n=n,
            )
        except Exception:
            await self.guard.rollback(user_id, estimate)
            raise
        total = sum((img.cost for img in generated), Decimal("0"))
        await self.guard.reconcile(user_id, reserved=estimate, actual=total)
        return ListingResult(
            prompt=final_prompt,
            used_model=ModelName.GPT_IMAGE_2,
            images=tuple(generated),
            total_cost=total,
        )
