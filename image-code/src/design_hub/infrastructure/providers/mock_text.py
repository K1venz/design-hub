"""确定性 mock 文本 LLM（前端联调 / CI 用，is_live=False）。

非真实推理：按关键词 + 可用 upload_ids 规则产出 tool_call 或澄清文本，
目的是让 ChatOrchestrator 与 /chat SSE 全链在无 key 时即可跑通、供 frontend-b 联调。
key 落定后由 OpenAICompatTextProvider 顶替（LSP 可替换）。
"""

import re
from collections.abc import AsyncIterator

from design_hub.ports.model_calls import ModelCallContext
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
_RATIO_RE = re.compile(
    r"(?<!\d)(1|3|4|9|16)\s*(?:[:：xX×]|比)\s*(1|3|4|9|16)(?!\d)"
)
_AUTO_RATIO_RE = re.compile(r"本轮确定比例=(1:1|3:4|4:3|9:16|16:9)")
_EDIT_SOURCE_RE = re.compile(r"明确选定编辑底图 source_image_key=([^\s。]+)")
_EDIT_INTENT_WORDS = ("改", "换", "调整", "重做", "变成")
_SUPPORTED_RATIOS = frozenset({"1:1", "3:4", "4:3", "9:16", "16:9"})
_DIGITS = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7}
_REVERSE_PROMPT_RESULT = {
    "summary": "一张待分析的商品图片",
    "subject": "画面中的主要商品",
    "scene": "简洁的商品展示场景",
    "composition": "商品位于画面主体位置",
    "camera": "平视角度的商品摄影",
    "lighting": "均匀柔和的展示光线",
    "colors": ["商品原有配色", "中性背景色"],
    "style": "写实商业商品摄影",
    "visible_text": [],
    "constraints": ["保持商品主体、比例和主要外观不变"],
    "uncertainties": ["Mock 模式不执行真实视觉识别，结果仅用于联调"],
    "prompt_zh": "写实商业商品摄影，主体清晰，构图简洁，柔和均匀光线",
    "prompt_en": (
        "Realistic commercial product photography, clear subject, "
        "clean composition, soft even lighting"
    ),
}


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
        self,
        *,
        context: ModelCallContext,
        messages: list[ChatMessage],
        tools: list[ToolSpec],
    ) -> AsyncIterator[LLMChunk]:
        del context
        # 收尾轮（无工具）：orchestrator 喂 tool 结果摘要，产模板收尾语
        if not tools:
            async for chunk in self._stream("已完成 ✅ 图已生成，可在结果区查看。"):
                yield chunk
            return

        required_tools = [tool for tool in tools if tool.required]
        if (
            len(required_tools) == 1
            and required_tools[0].name == "return_reverse_prompt"
        ):
            yield ToolCallChunk((
                ToolCall(
                    id="mock_reverse_prompt_result",
                    name="return_reverse_prompt",
                    arguments=_REVERSE_PROMPT_RESULT,
                ),
            ))
            return

        text = _latest_user_text(messages)
        uids = _available_uploads(messages)
        ratio = _ratio_from_text(text)
        user_text = text.partition("\n\n[系统备注]")[0]
        edit_source = _EDIT_SOURCE_RE.search(text)

        if "反推提示词" in user_text or "反推这张" in user_text:
            if uids:
                yield ToolCallChunk((
                    ToolCall(
                        id="mock_reverse_prompt",
                        name="reverse_prompt",
                        arguments={
                            "source": {
                                "kind": "upload",
                                "upload_id": uids[0],
                            }
                        },
                    ),
                ))
                return
            async for chunk in self._stream("请先添加一张需要分析的图片。"):
                yield chunk
            return

        if "打开换背景" in user_text or "进入换背景" in user_text:
            arguments: dict[str, object] = {"feature": "background_replace"}
            if uids:
                arguments["source"] = {
                    "kind": "upload",
                    "upload_id": uids[0],
                }
            yield ToolCallChunk((
                ToolCall(
                    id="mock_open_background",
                    name="open_feature",
                    arguments=arguments,
                ),
            ))
            return

        if edit_source and any(word in user_text for word in _EDIT_INTENT_WORDS):
            async for chunk in self._stream("好的，我会基于你选中的图片继续调整。"):
                yield chunk
            yield ToolCallChunk((
                ToolCall(
                    id="mock_edit",
                    name="edit",
                    arguments={
                        "source_image_key": edit_source.group(1),
                        "prompt": user_text,
                        "edit_mode": "delta",
                    },
                ),
            ))
            return

        if "换背景" in user_text or "更换背景" in user_text:
            if not uids:
                async for chunk in self._stream("请先添加一张需要换背景的商品图。"):
                    yield chunk
                return
            background: dict[str, str]
            if len(uids) >= 2:
                background = {
                    "kind": "reference",
                    "upload_id": uids[1],
                    "instruction": user_text,
                }
            else:
                background = {
                    "kind": "description",
                    "description": user_text,
                }
            async for chunk in self._stream("好的，我来帮你更换背景。"):
                yield chunk
            yield ToolCallChunk((
                ToolCall(
                    id="mock_replace_background",
                    name="replace_background",
                    arguments={
                        "source": {
                            "kind": "upload",
                            "upload_id": uids[0],
                        },
                        "background": background,
                    },
                ),
            ))
            return

        if any(k in text for k in ("复刻", "爆款", "照这张", "同款")):
            if len(uids) >= 2:
                async for chunk in self._stream("好的，我按爆款版式帮你复刻。"):
                    yield chunk
                yield ToolCallChunk((ToolCall(
                    id="mock_clone",
                    name="clone",
                    arguments={
                        "clone_mode": "参考风格",
                        "ratio": ratio,
                        "prompt": text,
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
                    "prompt": text,
                    "ratio": ratio,
                    "plan": {"白底": 1, "场景": 2, "卖点": 2},
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
                    "prompt": text,
                    "ratio": ratio,
                    "n": _count_from_text(text),
                },
            ),))
            return

        async for chunk in self._stream("请描述你想要的设计，并点『＋添加图片』上传产品图。"):
            yield chunk

    async def _stream(self, text: str) -> AsyncIterator[LLMChunk]:
        # 切块模拟 token 流，让前端看到增量气泡
        for i in range(0, len(text), 6):
            yield TextChunk(text[i : i + 6])
