import re
from dataclasses import dataclass
from enum import StrEnum

SUPPORTED_CHAT_RATIOS = ("1:1", "3:4", "4:3", "9:16", "16:9")
_SUPPORTED_SET = frozenset(SUPPORTED_CHAT_RATIOS)
_EXPLICIT_RATIO_RE = re.compile(
    r"(?<!\d)([1-9]\d*)\s*(?:[:：/xX×]|比)\s*([1-9]\d*)(?!\d)"
)
_LANDSCAPE_WORDS = ("横版", "横图", "横向构图")


class ChatRatioSource(StrEnum):
    EXPLICIT = "explicit"
    ORIENTATION = "orientation"
    AUTO = "auto"
    UNSUPPORTED = "unsupported"


class UnsupportedChatRatio(ValueError):
    pass


@dataclass(frozen=True)
class ChatRatioDecision:
    ratio: str | None
    source: ChatRatioSource
    requested: str | None = None

    @property
    def changes_edit_ratio(self) -> bool:
        return self.source in {
            ChatRatioSource.EXPLICIT,
            ChatRatioSource.ORIENTATION,
        }

    def require_supported(self) -> str:
        if self.ratio is not None:
            return self.ratio
        options = " / ".join(SUPPORTED_CHAT_RATIOS)
        raise UnsupportedChatRatio(
            f"当前支持的图片比例是 {options}，你写的 {self.requested} 暂不支持，请选择其中一种。"
        )


def decide_chat_ratio(message: str, auto_ratio: str) -> ChatRatioDecision:
    if auto_ratio not in _SUPPORTED_SET:
        raise ValueError(f"无效自动比例：{auto_ratio}")
    match = _EXPLICIT_RATIO_RE.search(message)
    if match is not None:
        requested = f"{match.group(1)}:{match.group(2)}"
        if requested in _SUPPORTED_SET:
            return ChatRatioDecision(requested, ChatRatioSource.EXPLICIT, requested)
        return ChatRatioDecision(None, ChatRatioSource.UNSUPPORTED, requested)
    if any(word in message for word in _LANDSCAPE_WORDS):
        return ChatRatioDecision("4:3", ChatRatioSource.ORIENTATION)
    return ChatRatioDecision(auto_ratio, ChatRatioSource.AUTO)
