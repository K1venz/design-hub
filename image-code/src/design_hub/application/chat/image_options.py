from dataclasses import dataclass
from enum import StrEnum

from design_hub.application.chat.ratio_intent import SUPPORTED_CHAT_RATIOS
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
            if self.count != 1:
                raise ValueError("4K 当前单次只能生成 1 张图片。")

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
