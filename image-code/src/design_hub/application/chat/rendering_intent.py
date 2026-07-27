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
    rf"(?:不要(?:生成)?|不需要(?:做成)?|无需|不用(?:改成)?|别用|不是)"
    rf"\s*(?:一张|这张|图片)?\s*{_FOUR_K_TOKEN}"
)
_EXPLICIT_FOUR_K_RE = re.compile(_FOUR_K_TOKEN)
_CLAUSE_SEPARATOR_RE = re.compile(r"(?:[，。；;！？!?\n]+|但是|但|不过|然而|而是)")


@dataclass(frozen=True)
class ChatRenderingDecision:
    model: ModelName
    ratio: ChatRatioDecision


class ChatRenderingConflict(ValueError):
    pass


def _positive_four_k_text(message: str) -> str:
    clauses = _CLAUSE_SEPARATOR_RE.split(message)
    return "，".join(
        clause for clause in clauses if _NEGATED_FOUR_K_RE.search(clause) is None
    )


def decide_chat_ratio_note(message: str, auto_ratio: str) -> ChatRatioDecision:
    """Build the ratio note before the LLM chooses whether to use a write tool."""
    if _EXPLICIT_FOUR_K_RE.search(_positive_four_k_text(message)) is not None:
        return ChatRatioDecision("16:9", ChatRatioSource.EXPLICIT, "16:9")
    return decide_chat_ratio(message, auto_ratio)


def decide_chat_rendering(message: str, auto_ratio: str) -> ChatRenderingDecision:
    positive_four_k_text = _positive_four_k_text(message)
    if _EXPLICIT_FOUR_K_RE.search(positive_four_k_text) is None:
        return ChatRenderingDecision(
            ModelName.GPT_IMAGE_2,
            decide_chat_ratio(message, auto_ratio),
        )

    explicit_ratio = extract_explicit_chat_ratio(positive_four_k_text)
    if explicit_ratio is not None and explicit_ratio.ratio is None:
        return ChatRenderingDecision(ModelName.GPT_IMAGE_2_4K, explicit_ratio)
    if explicit_ratio is not None and explicit_ratio.ratio != "16:9":
        raise ChatRenderingConflict(FOUR_K_RATIO_CONFLICT_MESSAGE)
    return ChatRenderingDecision(
        ModelName.GPT_IMAGE_2_4K,
        ChatRatioDecision("16:9", ChatRatioSource.EXPLICIT, "16:9"),
    )
