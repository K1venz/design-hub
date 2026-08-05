from dataclasses import dataclass
from enum import StrEnum
from math import log

from design_hub.application.chat.ratio_intent import (
    ChatRatioDecision,
    ChatRatioSource,
)
from design_hub.domain.image_capabilities import (
    image_model_capabilities,
    supported_image_ratios,
)
from design_hub.domain.tasking import RenderTier


class ChatRenderTier(StrEnum):
    AUTO = "auto"
    STANDARD = "standard"
    TWO_K = "2k"
    FOUR_K = "4k"


@dataclass(frozen=True)
class ChatImageOptions:
    render_tier: ChatRenderTier
    ratio: str
    count: int | None

    def __post_init__(self) -> None:
        if self.ratio != "auto" and self.ratio not in supported_image_ratios():
            raise ValueError(f"不支持的图片比例：{self.ratio}")
        if self.count is not None and not 1 <= self.count <= 7:
            raise ValueError("单次只能生成 1–7 张图片。")

    def validate_for(
        self,
        *,
        model_id: str,
        render_tier: RenderTier,
        resolved_ratio: str,
        resolved_count: int,
    ) -> None:
        capabilities = image_model_capabilities(model_id)
        ratios = capabilities.ratios(render_tier)
        if resolved_ratio not in ratios:
            options = " / ".join(ratios)
            raise ValueError(
                f"{model_id} {render_tier.value} 不支持 {resolved_ratio}，"
                f"可选比例是 {options}。"
            )
        if not 1 <= resolved_count <= capabilities.platform_max_count:
            raise ValueError(
                f"{model_id} 单次只能生成 "
                f"1–{capabilities.platform_max_count} 张图片。"
            )

    def resolve_ratio_for(
        self,
        *,
        model_id: str,
        render_tier: RenderTier,
        decision: ChatRatioDecision,
    ) -> ChatRatioDecision:
        if decision.ratio is None:
            return decision
        ratios = image_model_capabilities(model_id).ratios(render_tier)
        if decision.ratio in ratios:
            return decision
        if self.ratio == "auto" and decision.source in {
            ChatRatioSource.AUTO,
            ChatRatioSource.ORIENTATION,
        }:
            closest = _closest_ratio(decision.ratio, ratios)
            return ChatRatioDecision(
                closest,
                (
                    ChatRatioSource.EXPLICIT
                    if closest != decision.ratio
                    else decision.source
                ),
                decision.requested,
            )
        options = " / ".join(ratios)
        raise ValueError(
            f"{model_id} {render_tier.value} 不支持 {decision.ratio}，"
            f"可选比例是 {options}。"
        )

    @property
    def fixed_render_tier(self) -> RenderTier | None:
        if self.render_tier is ChatRenderTier.AUTO:
            return None
        if self.render_tier is ChatRenderTier.STANDARD:
            return RenderTier.STANDARD
        if self.render_tier is ChatRenderTier.TWO_K:
            return RenderTier.TWO_K
        return RenderTier.FOUR_K


def _closest_ratio(ratio: str, candidates: tuple[str, ...]) -> str:
    width, height = (int(part) for part in ratio.split(":"))
    target = width / height

    def distance(candidate: str) -> float:
        candidate_width, candidate_height = (
            int(part) for part in candidate.split(":")
        )
        return abs(log(target / (candidate_width / candidate_height)))

    return min(candidates, key=distance)


AUTO_CHAT_IMAGE_OPTIONS = ChatImageOptions(
    render_tier=ChatRenderTier.AUTO,
    ratio="auto",
    count=None,
)
