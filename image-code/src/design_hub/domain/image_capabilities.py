from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from design_hub.domain.gpt_image_2 import (
    GPT_IMAGE_2_FOUR_K_RATIO_SIZES,
    GPT_IMAGE_2_MODEL_ID,
    GPT_IMAGE_2_STANDARD_RATIO_SIZES,
)
from design_hub.domain.model_config import WAN_2_7_IMAGE_PRO
from design_hub.domain.nano_banana import (
    NANO_BANANA_2_MODEL_ID,
    NANO_BANANA_RATIO_SIZES,
)
from design_hub.domain.tasking import RenderTier
from design_hub.domain.wan_image import WAN_TIER_RATIO_SIZES


@dataclass(frozen=True)
class ImageOutputSpec:
    ratio: str
    render_tier: RenderTier
    size: tuple[int, int]


@dataclass(frozen=True)
class ImageModelCapabilities:
    model_id: str
    tier_ratio_sizes: Mapping[RenderTier, Mapping[str, tuple[int, int]]]
    platform_max_count: int
    provider_max_count: int
    reference_supported_tiers: frozenset[RenderTier]

    @property
    def supported_tiers(self) -> tuple[RenderTier, ...]:
        return tuple(self.tier_ratio_sizes)

    def ratios(self, render_tier: RenderTier) -> tuple[str, ...]:
        try:
            return tuple(self.tier_ratio_sizes[render_tier])
        except KeyError:
            raise ValueError(
                f"{self.model_id} does not support render tier {render_tier.value}"
            ) from None

    def output_for(self, render_tier: RenderTier, ratio: str) -> ImageOutputSpec:
        try:
            sizes = self.tier_ratio_sizes[render_tier]
        except KeyError:
            raise ValueError(
                f"{self.model_id} does not support render tier {render_tier.value}"
            ) from None
        try:
            size = sizes[ratio]
        except KeyError:
            options = " / ".join(sizes)
            raise ValueError(
                f"{self.model_id} {render_tier.value} 不支持 {ratio}，"
                f"可选比例：{options}"
            ) from None
        return ImageOutputSpec(ratio=ratio, render_tier=render_tier, size=size)

    def supports_references_for(self, render_tier: RenderTier) -> bool:
        self.ratios(render_tier)
        return render_tier in self.reference_supported_tiers

    def validate_operation(
        self,
        render_tier: RenderTier,
        ratio: str,
        *,
        has_references: bool,
    ) -> ImageOutputSpec:
        output = self.output_for(render_tier, ratio)
        if has_references and not self.supports_references_for(render_tier):
            raise ValueError(
                f"{self.model_id} does not support references at "
                f"{render_tier.value}"
            )
        return output


_GPT_TIER_RATIO_SIZES: Mapping[
    RenderTier, Mapping[str, tuple[int, int]]
] = MappingProxyType(
    {
        RenderTier.STANDARD: GPT_IMAGE_2_STANDARD_RATIO_SIZES,
        RenderTier.FOUR_K: GPT_IMAGE_2_FOUR_K_RATIO_SIZES,
    }
)

_CAPABILITIES: Mapping[str, ImageModelCapabilities] = MappingProxyType(
    {
        GPT_IMAGE_2_MODEL_ID: ImageModelCapabilities(
            model_id=GPT_IMAGE_2_MODEL_ID,
            tier_ratio_sizes=_GPT_TIER_RATIO_SIZES,
            platform_max_count=7,
            provider_max_count=1,
            reference_supported_tiers=frozenset(_GPT_TIER_RATIO_SIZES),
        ),
        NANO_BANANA_2_MODEL_ID: ImageModelCapabilities(
            model_id=NANO_BANANA_2_MODEL_ID,
            tier_ratio_sizes=NANO_BANANA_RATIO_SIZES,
            platform_max_count=7,
            provider_max_count=1,
            reference_supported_tiers=frozenset(NANO_BANANA_RATIO_SIZES),
        ),
        WAN_2_7_IMAGE_PRO: ImageModelCapabilities(
            model_id=WAN_2_7_IMAGE_PRO,
            tier_ratio_sizes=WAN_TIER_RATIO_SIZES,
            platform_max_count=7,
            provider_max_count=1,
            reference_supported_tiers=frozenset(
                {RenderTier.STANDARD, RenderTier.TWO_K}
            ),
        ),
    }
)


def image_model_capabilities(model_id: str) -> ImageModelCapabilities:
    try:
        return _CAPABILITIES[model_id]
    except KeyError:
        raise ValueError(f"unsupported image model: {model_id}") from None


def supported_image_ratios() -> tuple[str, ...]:
    ordered: dict[str, None] = {}
    for capabilities in _CAPABILITIES.values():
        for tier in capabilities.supported_tiers:
            for ratio in capabilities.ratios(tier):
                ordered.setdefault(ratio, None)
    return tuple(ordered)
