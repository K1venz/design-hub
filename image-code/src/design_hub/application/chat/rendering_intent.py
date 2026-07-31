import re
from dataclasses import dataclass

from design_hub.application.chat.ratio_intent import (
    ChatRatioDecision,
    ChatRatioSource,
    decide_chat_ratio,
    extract_explicit_chat_ratio,
)
from design_hub.domain.tasking import RenderTier

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
class _FourKIntent:
    requested: bool | None
    scope_text: str


@dataclass(frozen=True)
class ChatRenderingDecision:
    render_tier: RenderTier
    ratio: ChatRatioDecision


class ChatRenderingConflict(ValueError):
    pass


def _resolve_four_k_intent(message: str) -> _FourKIntent:
    requested: bool | None = None
    scope_start = 0
    clause_start = 0

    for separator in _CLAUSE_SEPARATOR_RE.finditer(message):
        clause = message[clause_start : separator.start()]
        if _EXPLICIT_FOUR_K_RE.search(clause) is not None:
            requested = _NEGATED_FOUR_K_RE.search(clause) is None
            scope_start = clause_start
        clause_start = separator.end()

    final_clause = message[clause_start:]
    if _EXPLICIT_FOUR_K_RE.search(final_clause) is not None:
        requested = _NEGATED_FOUR_K_RE.search(final_clause) is None
        scope_start = clause_start

    if requested is None:
        return _FourKIntent(None, message)
    return _FourKIntent(requested, message[scope_start:])


def decide_chat_ratio_note(message: str, auto_ratio: str) -> ChatRatioDecision:
    """Build the ratio note before the LLM chooses whether to use a write tool."""
    intent = _resolve_four_k_intent(message)
    if intent.requested is True:
        return ChatRatioDecision("16:9", ChatRatioSource.EXPLICIT, "16:9")
    return decide_chat_ratio(intent.scope_text, auto_ratio)


def decide_chat_rendering(message: str, auto_ratio: str) -> ChatRenderingDecision:
    intent = _resolve_four_k_intent(message)
    if intent.requested is not True:
        return ChatRenderingDecision(
            RenderTier.STANDARD,
            decide_chat_ratio(intent.scope_text, auto_ratio),
        )

    explicit_ratio = extract_explicit_chat_ratio(intent.scope_text)
    if explicit_ratio is not None and explicit_ratio.ratio is None:
        return ChatRenderingDecision(RenderTier.FOUR_K, explicit_ratio)
    if explicit_ratio is not None and explicit_ratio.ratio != "16:9":
        raise ChatRenderingConflict(FOUR_K_RATIO_CONFLICT_MESSAGE)
    return ChatRenderingDecision(
        RenderTier.FOUR_K,
        ChatRatioDecision("16:9", ChatRatioSource.EXPLICIT, "16:9"),
    )
