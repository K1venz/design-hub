import re
from dataclasses import dataclass

from design_hub.application.chat.ratio_intent import (
    ChatRatioDecision,
    ChatRatioSource,
    decide_chat_ratio,
    extract_explicit_chat_ratio,
)
from design_hub.domain.enums import ModelName

FOUR_K_RATIO_CONFLICT_MESSAGE = (
    "4K 当前仅支持 16:9 横版（3840×2160）。"
    "你可以选择继续生成 4K 16:9，或取消 4K 后按本次指定比例生成。"
)

_FOUR_K_TOKEN = (
    r"(?:(?<!\d)4\s*[kK](?![A-Za-z0-9])|(?<!\d)3840\s*[xX×]\s*2160(?!\d))"
)
_NEGATED_FOUR_K_RE = re.compile(
    rf"(?:不要|不需要|无需|不用)\s*{_FOUR_K_TOKEN}"
)
_EXPLICIT_FOUR_K_RE = re.compile(_FOUR_K_TOKEN)


@dataclass(frozen=True)
class ChatRenderingDecision:
    model: ModelName
    ratio: ChatRatioDecision


class ChatRenderingConflict(ValueError):
    pass


def decide_chat_rendering(message: str, auto_ratio: str) -> ChatRenderingDecision:
    if _NEGATED_FOUR_K_RE.search(message) is not None:
        return ChatRenderingDecision(
            ModelName.GPT_IMAGE_2,
            decide_chat_ratio(message, auto_ratio),
        )
    if _EXPLICIT_FOUR_K_RE.search(message) is None:
        return ChatRenderingDecision(
            ModelName.GPT_IMAGE_2,
            decide_chat_ratio(message, auto_ratio),
        )

    explicit_ratio = extract_explicit_chat_ratio(message)
    if explicit_ratio is not None and explicit_ratio.ratio != "16:9":
        raise ChatRenderingConflict(FOUR_K_RATIO_CONFLICT_MESSAGE)
    return ChatRenderingDecision(
        ModelName.GPT_IMAGE_2_4K,
        ChatRatioDecision("16:9", ChatRatioSource.EXPLICIT, "16:9"),
    )
