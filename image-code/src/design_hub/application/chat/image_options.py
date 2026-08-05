from dataclasses import dataclass
from enum import StrEnum

from design_hub.application.chat.ratio_intent import (
    SUPPORTED_CHAT_RATIOS,
    ChatRatioDecision,
    ChatRatioSource,
)
from design_hub.domain.gpt_image_2 import (
    GPT_IMAGE_2_MODEL_ID,
    gpt_image_2_contract,
)
from design_hub.domain.tasking import RenderTier


class ChatRenderTier(StrEnum):
    AUTO = "auto"
    STANDARD = "standard"
    FOUR_K = "4k"


@dataclass(frozen=True)
class ChatImageOptions:
    render_tier: ChatRenderTier
    ratio: str
    count: int | None

    def __post_init__(self) -> None:
        if self.ratio != "auto" and self.ratio not in SUPPORTED_CHAT_RATIOS:
            raise ValueError(f"不支持的图片比例：{self.ratio}")
        if self.count is not None and not 1 <= self.count <= 7:
            raise ValueError("标准档单次只能生成 1–7 张图片。")
        if self.render_tier is ChatRenderTier.FOUR_K:
            if self.ratio != "16:9":
                raise ValueError("4K 当前仅支持 16:9 横版（3840×2160）。")

    def validate_for(
        self,
        *,
        model_id: str,
        render_tier: RenderTier,
        resolved_ratio: str,
        resolved_count: int,
    ) -> None:
        if model_id != GPT_IMAGE_2_MODEL_ID:
            return
        contract = gpt_image_2_contract(render_tier)
        if resolved_ratio not in contract.ratios:
            options = " / ".join(contract.ratios)
            raise ValueError(
                f"GPT Image 2 {render_tier.value} 当前支持的比例是 {options}。"
            )
        if not 1 <= resolved_count <= contract.platform_max_count:
            raise ValueError(
                f"GPT Image 2 单次只能生成 1–{contract.platform_max_count} 张图片。"
            )

    def resolve_ratio_for(
        self,
        *,
        model_id: str,
        render_tier: RenderTier,
        decision: ChatRatioDecision,
    ) -> ChatRatioDecision:
        if model_id != GPT_IMAGE_2_MODEL_ID or decision.ratio is None:
            return decision
        contract = gpt_image_2_contract(render_tier)
        if decision.ratio in contract.ratios:
            return decision
        if (
            render_tier is RenderTier.STANDARD
            and self.ratio == "auto"
            and decision.source in {ChatRatioSource.AUTO, ChatRatioSource.ORIENTATION}
        ):
            width, height = (int(part) for part in decision.ratio.split(":"))
            mapped_ratio = "3:2" if width > height else "1:1"
            return ChatRatioDecision(
                mapped_ratio,
                decision.source,
                decision.requested,
            )
        return decision

    @property
    def fixed_render_tier(self) -> RenderTier | None:
        if self.render_tier is ChatRenderTier.AUTO:
            return None
        if self.render_tier is ChatRenderTier.STANDARD:
            return RenderTier.STANDARD
        return RenderTier.FOUR_K


AUTO_CHAT_IMAGE_OPTIONS = ChatImageOptions(
    render_tier=ChatRenderTier.AUTO,
    ratio="auto",
    count=None,
)
