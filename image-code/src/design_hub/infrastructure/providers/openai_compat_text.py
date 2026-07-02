"""OpenAI 兼容文本 LLM 适配器（DeepSeek / apinebula 文本模型等）。

流式 chat/completions + tool calling。与具体供应商解耦，只认 base_url + api_key + model。
⚠️ 待用户拍板文本 key/access 后方可真联调（现阶段全链用 MockTextLLMProvider）；
本适配器契约=标准 OpenAI 流式协议，DeepSeek 亦遵循。
"""

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from design_hub.ports.text_llm import (
    ChatMessage,
    LLMChunk,
    TextChunk,
    TextLLMError,
    TextLLMPort,
    ToolCall,
    ToolCallChunk,
    ToolSpec,
)


class OpenAICompatTextProvider(TextLLMPort):
    """对 OpenAI chat/completions 标准协议编程的文本 LLM Provider。"""

    is_live = True

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        client: httpx.AsyncClient | None = None,
        timeout: float = 120.0,
        trust_env: bool = False,
        extra_body: dict[str, Any] | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        if not api_key:
            raise ValueError("api_key 不能为空")
        self._api_key = api_key
        self._model = model
        self._client = client
        # connect 快失败(≤15s)，read 容忍慢首 token
        self._timeout = httpx.Timeout(timeout, connect=min(timeout, 15.0))
        self._trust_env = trust_env
        # 供应商特定透传参（如火山 ARK thinking 模型的 thinking:{"type":"disabled"} 关思考提速）；
        # 装配层注入，adapter 本身保持 provider 无关。
        self._extra_body = extra_body or {}

    async def complete(
        self, *, messages: list[ChatMessage], tools: list[ToolSpec]
    ) -> AsyncIterator[LLMChunk]:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [self._to_openai_msg(m) for m in messages],
            "stream": True,
            **self._extra_body,  # 供应商特定参（thinking 开关等）
        }
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]
            payload["tool_choice"] = "auto"
        headers = {"Authorization": f"Bearer {self._api_key}"}
        url = f"{self._base_url}/chat/completions"
        # index -> {"id", "name", "args"}：工具调用参数按 index 跨 chunk 拼接
        acc: dict[int, dict[str, str]] = {}
        try:
            async for line in self._iter_lines(url, payload, headers):
                if not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                if data == "[DONE]":
                    break
                delta = self._delta(data)
                if delta is None:
                    continue
                # 只取 content；thinking 模型（火山 ARK doubao 等）的内部推理在
                # delta["reasoning_content"]——刻意不读，绝不混进用户可见的 assistant_delta。
                content = delta.get("content")
                if content:
                    yield TextChunk(content)
                for frag in delta.get("tool_calls") or []:
                    idx = frag.get("index", 0)
                    slot = acc.setdefault(idx, {"id": "", "name": "", "args": ""})
                    if frag.get("id"):
                        slot["id"] = frag["id"]
                    fn = frag.get("function") or {}
                    if fn.get("name"):
                        slot["name"] = fn["name"]
                    if fn.get("arguments"):
                        slot["args"] += fn["arguments"]
        except httpx.HTTPError as exc:
            raise TextLLMError(f"文本 LLM 传输错误：{exc}") from exc
        if acc:
            calls = tuple(
                ToolCall(
                    id=s["id"] or s["name"],
                    name=s["name"],
                    arguments=self._parse_args(s["args"]),
                )
                for _, s in sorted(acc.items())
                if s["name"]
            )
            if calls:
                yield ToolCallChunk(calls)

    async def _iter_lines(
        self, url: str, payload: dict[str, Any], headers: dict[str, str]
    ) -> AsyncIterator[str]:
        if self._client is not None:
            async with self._client.stream(
                "POST", url, json=payload, headers=headers, timeout=self._timeout
            ) as resp:
                self._raise_for_status(resp)
                async for line in resp.aiter_lines():
                    yield line
            return
        async with httpx.AsyncClient(timeout=self._timeout, trust_env=self._trust_env) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as resp:
                self._raise_for_status(resp)
                async for line in resp.aiter_lines():
                    yield line

    def _raise_for_status(self, resp: httpx.Response) -> None:
        if 200 <= resp.status_code < 300:
            return
        raise TextLLMError(f"文本 LLM {resp.status_code}: {resp.reason_phrase}")

    @staticmethod
    def _delta(data: str) -> dict[str, Any] | None:
        try:
            body = json.loads(data)
        except json.JSONDecodeError:
            return None
        choices = body.get("choices") or []
        if not choices:
            return None
        delta = choices[0].get("delta")
        return delta if isinstance(delta, dict) else None

    @staticmethod
    def _parse_args(raw: str) -> dict[str, Any]:
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise TextLLMError(f"工具参数非合法 JSON：{raw[:200]}") from exc
        if not isinstance(parsed, dict):
            raise TextLLMError(f"工具参数需为对象：{raw[:200]}")
        return parsed

    @staticmethod
    def _to_openai_msg(m: ChatMessage) -> dict[str, Any]:
        msg: dict[str, Any] = {"role": m.role, "content": m.content}
        if m.tool_call_id:
            msg["tool_call_id"] = m.tool_call_id
        if m.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                    },
                }
                for tc in m.tool_calls
            ]
        return msg
