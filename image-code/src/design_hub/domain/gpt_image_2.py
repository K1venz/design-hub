from dataclasses import dataclass

from design_hub.domain.tasking import RenderTier

GPT_IMAGE_2_MODEL_ID = "gpt-image-2"
GPT_IMAGE_2_FOUR_K_MODEL = "gpt-image-2-4k"


@dataclass(frozen=True)
class GptImage2ApiContract:
    upstream_model: str
    ratios: tuple[str, ...]
    generation_sizes: frozenset[tuple[int, int]]
    edit_sizes: frozenset[tuple[int, int]]
    provider_max_count: int
    platform_max_count: int
    required_quality: str | None = None

    def validate_request(
        self,
        *,
        size: tuple[int, int],
        count: int,
        has_references: bool,
    ) -> None:
        supported_sizes = self.edit_sizes if has_references else self.generation_sizes
        if size not in supported_sizes:
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


GPT_IMAGE_2_API_CONTRACTS: dict[RenderTier, GptImage2ApiContract] = {
    RenderTier.STANDARD: GptImage2ApiContract(
        upstream_model=GPT_IMAGE_2_MODEL_ID,
        ratios=("1:1", "3:2"),
        generation_sizes=frozenset({(1024, 1024)}),
        edit_sizes=frozenset({(1024, 1024), (1536, 1024)}),
        provider_max_count=1,
        platform_max_count=7,
    ),
    RenderTier.FOUR_K: GptImage2ApiContract(
        upstream_model=GPT_IMAGE_2_FOUR_K_MODEL,
        ratios=("16:9",),
        generation_sizes=frozenset({(3840, 2160)}),
        edit_sizes=frozenset({(3840, 2160)}),
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
