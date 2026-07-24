"""确定性 mock 文本 LLM（前端联调 / CI 用，is_live=False）。

非真实推理：按关键词 + 可用 upload_ids 规则产出 tool_call 或澄清文本，
目的是让 ChatOrchestrator 与 /chat SSE 全链在无 key 时即可跑通、供 frontend-b 联调。
key 落定后由 OpenAICompatTextProvider 顶替（LSP 可替换）。
"""

import re
from collections.abc import AsyncIterator

from design_hub.ports.text_llm import (
    ChatMessage,
    LLMChunk,
    TextChunk,
    TextLLMPort,
    ToolCall,
    ToolCallChunk,
    ToolSpec,
)

_UPLOAD_RE = re.compile(r"upload_ids=([\w,\-/.]+)")  # id=<ns>/<sha>.<ext>，含 / 与 .
_RATIO_RE = re.compile(r"(?<!\d)(1|3|9|16)\s*(?:[:：xX×]|比)\s*(1|4|16|9)(?!\d)")
_AUTO_RATIO_RE = re.compile(r"自动比例=(1:1|3:4|9:16|16:9)")
_SUPPORTED_RATIOS = frozenset({"1:1", "3:4", "9:16", "16:9"})
_DIGITS = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7}


def _latest_user_text(messages: list[ChatMessage]) -> str:
    for m in reversed(messages):
        if m.role == "user":
            return m.content
    return ""


def _available_uploads(messages: list[ChatMessage]) -> list[str]:
    # 扫最近一条带 upload_ids 备注的 user 消息（orchestrator 注入本轮可用图）
    for m in reversed(messages):
        if m.role == "user":
            hit = _UPLOAD_RE.search(m.content)
            if hit:
                return [x for x in hit.group(1).split(",") if x]
    return []


def _count_from_text(text: str) -> int:
    hit = re.search(r"(\d+)\s*张", text)
    if hit:
        return max(1, min(7, int(hit.group(1))))
    for ch, val in _DIGITS.items():
        if f"{ch}张" in text:
            return val
    return 1


def _ratio_from_text(text: str) -> str:
    user_text = text.partition("\n\n[系统备注]")[0]
    for hit in _RATIO_RE.finditer(user_text):
        ratio = f"{hit.group(1)}:{hit.group(2)}"
        if ratio in _SUPPORTED_RATIOS:
            return ratio
    auto_ratio = _AUTO_RATIO_RE.search(text)
    return auto_ratio.group(1) if auto_ratio else "1:1"


class MockTextLLMProvider(TextLLMPort):
    """规则驱动的文本 LLM 替身。"""

    is_live = False

    async def complete(
        self, *, messages: list[ChatMessage], tools: list[ToolSpec]
    ) -> AsyncIterator[LLMChunk]:
        # 收尾轮（无工具）：orchestrator 喂 tool 结果摘要，产模板收尾语
        if not tools:
            async for chunk in self._stream("已完成 ✅ 图已生成，可在结果区查看。"):
                yield chunk
            return

        text = _latest_user_text(messages)
        uids = _available_uploads(messages)
        ratio = _ratio_from_text(text)

        if any(k in text for k in ("复刻", "爆款", "照这张", "同款")):
            if len(uids) >= 2:
                async for chunk in self._stream("好的，我按爆款版式帮你复刻。"):
                    yield chunk
                yield ToolCallChunk((ToolCall(
                    id="mock_clone",
                    name="clone",
                    arguments={
                        "product_upload_ids": [uids[0]],
                        "reference_upload_ids": uids[1:3],
                        "clone_mode": "参考风格",
                        "ratio": ratio,
                        "prompt": text,
                        "category": "FOOD",
                    },
                ),))
                return
            need = "复刻需要产品图 + 爆款参考图，请一起添加（至少 2 张）。"
            async for chunk in self._stream(need):
                yield chunk
            return

        if uids and any(k in text for k in ("套图", "一套", "整套")):
            async for chunk in self._stream("好的，我来帮你出一套图。"):
                yield chunk
            yield ToolCallChunk((ToolCall(
                id="mock_set",
                name="generate",
                arguments={
                    "upload_ids": uids[:3],
                    "prompt": text,
                    "ratio": ratio,
                    "plan": {"白底": 1, "场景": 2, "卖点": 2},
                    "category": "FOOD",
                },
            ),))
            return

        if uids:
            async for chunk in self._stream("好的，我来帮你出图。"):
                yield chunk
            yield ToolCallChunk((ToolCall(
                id="mock_gen",
                name="generate",
                arguments={
                    "upload_ids": uids[:3],
                    "prompt": text,
                    "ratio": ratio,
                    "n": _count_from_text(text),
                    "category": "FOOD",
                },
            ),))
            return

        async for chunk in self._stream("请描述你想要的设计，并点『＋添加图片』上传产品图。"):
            yield chunk

    async def _stream(self, text: str) -> AsyncIterator[LLMChunk]:
        # 切块模拟 token 流，让前端看到增量气泡
        for i in range(0, len(text), 6):
            yield TextChunk(text[i : i + 6])
