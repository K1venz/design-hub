"""OpenAICompatTextProvider 单测（火山 ARK/DeepSeek 等 OpenAI 兼容文本 LLM 适配器）。

无网络：httpx.MockTransport 注入流式 SSE。重点覆盖：
- thinking 模型 reasoning_content 过滤（只 content 出到 assistant，推理绝不泄漏）；
- tool_calls 跨 chunk 分片拼接 → ToolCallChunk（args JSON 正确解析）；
- extra_body（thinking 关等供应商参）透传进 payload；
- 非 2xx → TextLLMError（I/O 域，fail-fast）。
"""

import asyncio
import json

import httpx
import pytest

from design_hub.infrastructure.providers.openai_compat_text import OpenAICompatTextProvider
from design_hub.ports.text_llm import (
    ChatImage,
    ChatMessage,
    TextChunk,
    TextLLMError,
    ToolCallChunk,
    ToolSpec,
)


def _sse(*deltas: dict) -> bytes:
    """把若干 choices[0].delta 拼成 OpenAI 流式 SSE 字节。"""
    events = []
    for delta in deltas:
        body = {"choices": [{"delta": delta, "finish_reason": None}]}
        events.append(f"data: {json.dumps(body, ensure_ascii=False)}")
    events.append("data: [DONE]")
    return ("\n\n".join(events) + "\n\n").encode()


def _tc_delta(
    *, index: int = 0, id: str | None = None, name: str | None = None, args: str | None = None
) -> dict:
    """构造一条 tool_calls 流式分片 delta。"""
    fn: dict = {}
    if name is not None:
        fn["name"] = name
    if args is not None:
        fn["arguments"] = args
    frag: dict = {"index": index, "function": fn}
    if id is not None:
        frag["id"] = id
    return {"tool_calls": [frag]}


def _provider(content: bytes, *, captured: dict | None = None, status: int = 200, **kw):
    def handler(request: httpx.Request) -> httpx.Response:
        if captured is not None:
            captured["payload"] = json.loads(request.content)
        return httpx.Response(status, content=content)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return OpenAICompatTextProvider(
        base_url="http://ark.test/api/v3", api_key="k", model="ep-x", client=client, **kw
    )


async def _collect(provider: OpenAICompatTextProvider, tools: list[ToolSpec]):
    return [
        chunk
        async for chunk in provider.complete(
            messages=[ChatMessage(role="user", content="hi")], tools=tools
        )
    ]


def test_reasoning_content_is_filtered_only_content_surfaces() -> None:
    content = _sse(
        {"role": "assistant", "reasoning_content": "我先想想用户要什么"},
        {"reasoning_content": "继续推理..."},
        {"content": "你好"},
        {"content": "，很高兴帮你"},
    )
    chunks = asyncio.run(_collect(_provider(content), []))
    texts = [c.text for c in chunks if isinstance(c, TextChunk)]
    assert texts == ["你好", "，很高兴帮你"]  # reasoning_content 一个字都不出
    assert not any(isinstance(c, ToolCallChunk) for c in chunks)


def test_tool_calls_fragments_accumulate_across_chunks() -> None:
    content = _sse(
        _tc_delta(id="call_1", name="generate", args='{"upload'),
        _tc_delta(args='_ids":["ns/a.png"],"ratio":"1:1"}'),
    )
    chunks = asyncio.run(_collect(_provider(content), []))
    tool_chunks = [c for c in chunks if isinstance(c, ToolCallChunk)]
    assert len(tool_chunks) == 1
    (call,) = tool_chunks[0].tool_calls
    assert call.id == "call_1"
    assert call.name == "generate"
    assert call.arguments == {"upload_ids": ["ns/a.png"], "ratio": "1:1"}


def test_reasoning_only_during_tool_call_still_filtered() -> None:
    # 火山 ARK 实测：出图轮 content 空、推理在 reasoning_content、答案在 tool_calls
    content = _sse(
        {"reasoning_content": "用户要套图"},
        _tc_delta(id="c", name="generate", args="{}"),
    )
    chunks = asyncio.run(_collect(_provider(content), []))
    assert not any(isinstance(c, TextChunk) for c in chunks)  # 无文本泄漏
    assert any(isinstance(c, ToolCallChunk) for c in chunks)


def test_extra_body_merged_into_payload() -> None:
    captured: dict = {}
    provider = _provider(
        _sse({"content": "ok"}), captured=captured, extra_body={"thinking": {"type": "disabled"}}
    )
    tools = [ToolSpec("generate", "出图", {"type": "object", "properties": {}})]
    asyncio.run(_collect(provider, tools))
    assert captured["payload"]["thinking"] == {"type": "disabled"}
    assert captured["payload"]["stream"] is True
    assert captured["payload"]["model"] == "ep-x"
    assert captured["payload"]["tool_choice"] == "auto"


def test_image_message_serializes_real_bytes_as_data_url() -> None:
    captured: dict = {}
    provider = _provider(_sse({"content": "ok"}), captured=captured)

    async def run() -> None:
        chunks = [
            chunk
            async for chunk in provider.complete(
                messages=[
                    ChatMessage(
                        role="user",
                        content="分析这张图片",
                        images=(
                            ChatImage(
                                data=b"\x89PNG\r\n\x1a\n",
                                media_type="image/png",
                            ),
                        ),
                    )
                ],
                tools=[],
            )
        ]
        assert chunks == [TextChunk("ok")]

    asyncio.run(run())

    content = captured["payload"]["messages"][0]["content"]
    assert content == [
        {"type": "text", "text": "分析这张图片"},
        {
            "type": "image_url",
            "image_url": {
                "url": "data:image/png;base64,iVBORw0KGgo="
            },
        },
    ]


def test_required_tool_is_forced_by_name() -> None:
    captured: dict = {}
    provider = _provider(
        _sse(_tc_delta(id="result", name="return_result", args="{}")),
        captured=captured,
    )
    tools = [
        ToolSpec(
            "return_result",
            "Return the result",
            {"type": "object", "properties": {}},
            required=True,
        )
    ]

    asyncio.run(_collect(provider, tools))

    assert captured["payload"]["tool_choice"] == {
        "type": "function",
        "function": {"name": "return_result"},
    }


def test_non_2xx_raises_text_llm_error() -> None:
    provider = _provider(b"rate limited", status=429)
    with pytest.raises(TextLLMError):
        asyncio.run(_collect(provider, []))


def test_bad_tool_args_json_raises() -> None:
    content = _sse(_tc_delta(id="c", name="generate", args="{not json"))
    with pytest.raises(TextLLMError):
        asyncio.run(_collect(_provider(content), []))
