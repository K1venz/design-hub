"""文本 LLM 端口（方案 C）：给定对话 + 工具规格，流式产出 assistant token 与 tool_call。

零框架 tool-use：把出图端点当工具暴露给 LLM，LLM 只产**结构化 tool 参数**
（= /listing 请求体字段），最终图像 prompt 仍由卡链在 service 内组装（PRD 铁律①）。
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolCall:
    """LLM 发起的一次工具调用（arguments 已解析为 dict）。"""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ChatMessage:
    """对话消息（OpenAI chat 协议对齐）。tool 结果用 role='tool'+tool_call_id。"""

    role: str  # system | user | assistant | tool
    content: str
    tool_call_id: str | None = None
    tool_calls: tuple[ToolCall, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ToolSpec:
    """工具规格：name + 描述 + 参数 JSON Schema（取自请求 DTO 的 model_json_schema）。"""

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class TextChunk:
    """流式 assistant 文本增量。"""

    text: str


@dataclass(frozen=True)
class ToolCallChunk:
    """LLM 决定调用工具（本轮文本流结束后给出）。"""

    tool_calls: tuple[ToolCall, ...]


LLMChunk = TextChunk | ToolCallChunk


class TextLLMError(Exception):
    """文本 LLM 不可用/传输错（I/O 域，允许上层重试/明确报错，绝不装死）。"""


class TextLLMPort(ABC):
    """文本 LLM 适配端口（ISP：唯一抽象方法 complete，流式）。"""

    is_live: bool = True

    @abstractmethod
    def complete(
        self, *, messages: list[ChatMessage], tools: list[ToolSpec]
    ) -> AsyncIterator[LLMChunk]:
        """流式补全：先 yield 若干 TextChunk，若模型选择工具则末尾 yield 一个 ToolCallChunk。"""
        ...
