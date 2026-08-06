from collections.abc import Mapping
from types import MappingProxyType

from design_hub.domain.tasking import RenderTier

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

WAN_STANDARD_RATIO_SIZES: Mapping[str, tuple[int, int]] = MappingProxyType(
    {
        "1:1": (1280, 1280),
        "1:4": (640, 2560),
        "1:8": (448, 3584),
        "2:3": (1024, 1536),
        "3:2": (1536, 1024),
        "3:4": (1104, 1472),
        "4:3": (1472, 1104),
        "4:1": (2560, 640),
        "4:5": (1120, 1400),
        "5:4": (1400, 1120),
        "8:1": (3584, 448),
        "9:16": (960, 1696),
        "16:9": (1696, 960),
        "1:2": (896, 1792),
        "2:1": (1792, 896),
        "21:9": (1904, 816),
    }
)

WAN_TWO_K_RATIO_SIZES: Mapping[str, tuple[int, int]] = MappingProxyType(
    {
        "1:1": (2048, 2048),
        "1:4": (1024, 4096),
        "1:8": (704, 5632),
        "2:3": (1664, 2496),
        "3:2": (2496, 1664),
        "3:4": (1728, 2368),
        "4:3": (2368, 1728),
        "4:1": (4096, 1024),
        "4:5": (1792, 2240),
        "5:4": (2240, 1792),
        "8:1": (5632, 704),
        "9:16": (1536, 2688),
        "16:9": (2688, 1536),
        "1:2": (1440, 2880),
        "2:1": (2880, 1440),
        "21:9": (3080, 1320),
    }
)

WAN_FOUR_K_RATIO_SIZES: Mapping[str, tuple[int, int]] = MappingProxyType(
    {
        "1:1": (4096, 4096),
        "1:4": (2048, 8192),
        "1:8": (1408, 11264),
        "2:3": (3328, 4992),
        "3:2": (4992, 3328),
        "3:4": (3072, 4096),
        "4:3": (4096, 3072),
        "4:1": (8192, 2048),
        "4:5": (3584, 4480),
        "5:4": (4480, 3584),
        "8:1": (11264, 1408),
        "9:16": (2304, 4096),
        "16:9": (4096, 2304),
        "1:2": (2880, 5760),
        "2:1": (5760, 2880),
        "21:9": (6160, 2640),
    }
)

WAN_TIER_RATIO_SIZES: Mapping[
    RenderTier, Mapping[str, tuple[int, int]]
] = MappingProxyType(
    {
        RenderTier.STANDARD: WAN_STANDARD_RATIO_SIZES,
        RenderTier.TWO_K: WAN_TWO_K_RATIO_SIZES,
        RenderTier.FOUR_K: WAN_FOUR_K_RATIO_SIZES,
    }
)
