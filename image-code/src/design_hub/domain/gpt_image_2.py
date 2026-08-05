from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from design_hub.domain.tasking import RenderTier

GPT_IMAGE_2_MODEL_ID = "gpt-image-2"
GPT_IMAGE_2_FOUR_K_MODEL = "gpt-image-2-4k"


@dataclass(frozen=True)
class GptImage2ApiContract:
    upstream_model: str
    ratio_sizes: Mapping[str, tuple[int, int]]
    provider_max_count: int
    platform_max_count: int
    required_quality: str | None = None

    @property
    def ratios(self) -> tuple[str, ...]:
        return tuple(self.ratio_sizes)

    @property
    def supported_sizes(self) -> frozenset[tuple[int, int]]:
        return frozenset(self.ratio_sizes.values())

    def size_for_ratio(self, ratio: str) -> tuple[int, int]:
        try:
            return self.ratio_sizes[ratio]
        except KeyError:
            options = " / ".join(self.ratios)
            raise ValueError(
                f"不支持的比例：{ratio}（可选 {options}）"
            ) from None

    def validate_request(
        self,
        *,
        size: tuple[int, int],
        count: int,
        has_references: bool,
    ) -> None:
        if size not in self.supported_sizes:
            endpoint = "edits" if has_references else "generations"
            raise ValueError(
                f"{self.upstream_model} {endpoint} does not support size "
                f"{size[0]}x{size[1]}"
            )
        if not 1 <= count <= self.provider_max_count:
            raise ValueError(
                f"{self.upstream_model} requires n between 1 and "
                f"{self.provider_max_count}"
            )


GPT_IMAGE_2_STANDARD_RATIO_SIZES: Mapping[str, tuple[int, int]] = MappingProxyType(
    {
        "1:1": (1024, 1024),
        "3:2": (1536, 1024),
        "2:3": (1024, 1536),
        "3:4": (1152, 1536),
        "4:3": (1536, 1152),
        "9:16": (864, 1536),
        "16:9": (1536, 864),
        "4:5": (1024, 1280),
        "5:4": (1280, 1024),
        "1:2": (768, 1536),
        "2:1": (1536, 768),
    }
)

GPT_IMAGE_2_FOUR_K_RATIO_SIZES: Mapping[str, tuple[int, int]] = MappingProxyType(
    {"16:9": (3840, 2160)}
)

GPT_IMAGE_2_API_CONTRACTS: dict[RenderTier, GptImage2ApiContract] = {
    RenderTier.STANDARD: GptImage2ApiContract(
        upstream_model=GPT_IMAGE_2_MODEL_ID,
        ratio_sizes=GPT_IMAGE_2_STANDARD_RATIO_SIZES,
        provider_max_count=1,
        platform_max_count=7,
    ),
    RenderTier.FOUR_K: GptImage2ApiContract(
        upstream_model=GPT_IMAGE_2_FOUR_K_MODEL,
        ratio_sizes=GPT_IMAGE_2_FOUR_K_RATIO_SIZES,
        provider_max_count=10,
        platform_max_count=7,
        required_quality="high",
    ),
}

_CONTRACTS_BY_UPSTREAM_MODEL = {
    contract.upstream_model: contract
    for contract in GPT_IMAGE_2_API_CONTRACTS.values()
}


def gpt_image_2_contract(render_tier: RenderTier) -> GptImage2ApiContract:
    return GPT_IMAGE_2_API_CONTRACTS[render_tier]


def gpt_image_2_contract_for_upstream_model(
    upstream_model: str,
) -> GptImage2ApiContract | None:
    return _CONTRACTS_BY_UPSTREAM_MODEL.get(upstream_model)
