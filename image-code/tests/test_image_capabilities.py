from fractions import Fraction

import pytest

from design_hub.domain.image_capabilities import image_model_capabilities
from design_hub.domain.tasking import RenderTier

NANO_RATIOS = (
    "1:1",
    "1:4",
    "1:8",
    "2:3",
    "3:2",
    "3:4",
    "4:1",
    "4:3",
    "4:5",
    "5:4",
    "8:1",
    "9:16",
    "16:9",
    "21:9",
)

NANO_SIZES = {
    "standard": {
        "1:1": (1024, 1024),
        "1:4": (512, 2048),
        "1:8": (384, 3072),
        "2:3": (848, 1264),
        "3:2": (1264, 848),
        "3:4": (896, 1200),
        "4:1": (2048, 512),
        "4:3": (1200, 896),
        "4:5": (928, 1152),
        "5:4": (1152, 928),
        "8:1": (3072, 384),
        "9:16": (768, 1376),
        "16:9": (1376, 768),
        "21:9": (1584, 672),
    },
    "2k": {
        "1:1": (2048, 2048),
        "1:4": (1024, 4096),
        "1:8": (768, 6144),
        "2:3": (1696, 2528),
        "3:2": (2528, 1696),
        "3:4": (1792, 2400),
        "4:1": (4096, 1024),
        "4:3": (2400, 1792),
        "4:5": (1856, 2304),
        "5:4": (2304, 1856),
        "8:1": (6144, 768),
        "9:16": (1536, 2752),
        "16:9": (2752, 1536),
        "21:9": (3168, 1344),
    },
    "4k": {
        "1:1": (4096, 4096),
        "1:4": (2048, 8192),
        "1:8": (1536, 12288),
        "2:3": (3392, 5056),
        "3:2": (5056, 3392),
        "3:4": (3584, 4800),
        "4:1": (8192, 2048),
        "4:3": (4800, 3584),
        "4:5": (3712, 4608),
        "5:4": (4608, 3712),
        "8:1": (12288, 1536),
        "9:16": (3072, 5504),
        "16:9": (5504, 3072),
        "21:9": (6336, 2688),
    },
}

WAN_RATIOS = (
    "1:1",
    "1:4",
    "1:8",
    "2:3",
    "3:2",
    "3:4",
    "4:3",
    "4:1",
    "4:5",
    "5:4",
    "8:1",
    "9:16",
    "16:9",
    "1:2",
    "2:1",
    "21:9",
)

WAN_TIER_PIXEL_CEILINGS = {
    RenderTier.STANDARD: 1280 * 1280,
    RenderTier.TWO_K: 2048 * 2048,
    RenderTier.FOUR_K: 4096 * 4096,
}


def test_render_tier_includes_two_k() -> None:
    assert RenderTier.TWO_K.value == "2k"


def test_nano_banana_exposes_exact_documented_matrix() -> None:
    contract = image_model_capabilities("nano-banana-2")

    assert contract.supported_tiers == (
        RenderTier.STANDARD,
        RenderTier.TWO_K,
        RenderTier.FOUR_K,
    )
    for tier in contract.supported_tiers:
        assert contract.ratios(tier) == NANO_RATIOS
        for ratio, expected_size in NANO_SIZES[tier.value].items():
            output = contract.output_for(tier, ratio)
            assert output.ratio == ratio
            assert output.render_tier is tier
            assert output.size == expected_size


def test_gpt_image_two_rejects_two_k() -> None:
    contract = image_model_capabilities("gpt-image-2")

    with pytest.raises(ValueError, match="does not support render tier 2k"):
        contract.output_for(RenderTier.TWO_K, "1:1")


def test_wan_exposes_every_platform_ratio_at_each_official_tier() -> None:
    contract = image_model_capabilities("wan2.7-image-pro")

    assert contract.supported_tiers == (
        RenderTier.STANDARD,
        RenderTier.TWO_K,
        RenderTier.FOUR_K,
    )
    for tier in contract.supported_tiers:
        assert contract.ratios(tier) == WAN_RATIOS


def test_wan_sizes_respect_ratio_and_tier_pixel_contract() -> None:
    contract = image_model_capabilities("wan2.7-image-pro")

    for tier, pixel_ceiling in WAN_TIER_PIXEL_CEILINGS.items():
        for ratio in WAN_RATIOS:
            width, height = contract.output_for(tier, ratio).size
            expected = float(Fraction(ratio.replace(":", "/")))
            actual = width / height

            assert width > 0
            assert height > 0
            assert width * height <= pixel_ceiling
            assert abs(actual - expected) / expected <= 0.03


def test_wan_uses_explicit_extreme_1k_sizes() -> None:
    contract = image_model_capabilities("wan2.7-image-pro")

    assert contract.output_for(RenderTier.STANDARD, "1:4").size == (640, 2560)
    assert contract.output_for(RenderTier.STANDARD, "4:1").size == (2560, 640)
    assert contract.output_for(RenderTier.STANDARD, "1:8").size == (448, 3584)
    assert contract.output_for(RenderTier.STANDARD, "8:1").size == (3584, 448)


def test_wan_references_are_limited_to_1k_and_2k() -> None:
    contract = image_model_capabilities("wan2.7-image-pro")

    contract.validate_operation(
        RenderTier.STANDARD,
        "1:1",
        has_references=True,
    )
    contract.validate_operation(
        RenderTier.TWO_K,
        "1:1",
        has_references=True,
    )
    contract.validate_operation(
        RenderTier.FOUR_K,
        "1:1",
        has_references=False,
    )
    with pytest.raises(ValueError, match="does not support references at 4k"):
        contract.validate_operation(
            RenderTier.FOUR_K,
            "1:1",
            has_references=True,
        )

    assert contract.platform_max_count == 7
    assert contract.provider_max_count == 1


def test_unknown_image_model_has_no_implicit_fallback() -> None:
    with pytest.raises(ValueError, match="unsupported image model"):
        image_model_capabilities("missing-image-model")
