from collections.abc import Mapping
from types import MappingProxyType

from design_hub.domain.tasking import RenderTier

NANO_BANANA_2_MODEL_ID = "nano-banana-2"
NANO_BANANA_UPSTREAM_MODEL = "gemini-3.1-flash-image"

_ONE_K: Mapping[str, tuple[int, int]] = MappingProxyType(
    {
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
    }
)

_TWO_K: Mapping[str, tuple[int, int]] = MappingProxyType(
    {
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
    }
)

_FOUR_K: Mapping[str, tuple[int, int]] = MappingProxyType(
    {
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
    }
)

NANO_BANANA_RATIO_SIZES: Mapping[
    RenderTier, Mapping[str, tuple[int, int]]
] = MappingProxyType(
    {
        RenderTier.STANDARD: _ONE_K,
        RenderTier.TWO_K: _TWO_K,
        RenderTier.FOUR_K: _FOUR_K,
    }
)
