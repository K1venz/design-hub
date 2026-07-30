"""OpenAI 兼容文本 LLM 适配器（DeepSeek / apinebula 文本模型等）。

流式 chat/completions + tool calling。与具体供应商解耦，只认 base_url + api_key + model。
⚠️ 待用户拍板文本 key/access 后方可真联调（现阶段全链用 MockTextLLMProvider）；
本适配器契约=标准 OpenAI 流式协议，DeepSeek 亦遵循。
"""

import asyncio
import base64
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from design_hub.ports.model_calls import (
    ModelCallContext,
    ModelCallRecorder,
    ModelUsage,
)
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


class _UpstreamResponseError(TextLLMError):
    pass


class OpenAICompatTextProvider(TextLLMPort):
    """对 OpenAI chat/completions 标准协议编程的文本 LLM Provider。"""

    is_live = True

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        recorder: ModelCallRecorder,
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
        self._recorder = recorder
        self._client = client
        # connect 快失败(≤15s)，read 容忍慢首 token
        self._timeout = httpx.Timeout(timeout, connect=min(timeout, 15.0))
        self._trust_env = trust_env
        # 供应商特定透传参（如火山 ARK thinking 模型的 thinking:{"type":"disabled"} 关思考提速）；
        # 装配层注入，adapter 本身保持 provider 无关。
        self._extra_body = extra_body or {}

    async def complete(
        self,
        *,
        context: ModelCallContext,
        messages: list[ChatMessage],
        tools: list[ToolSpec],
    ) -> AsyncIterator[LLMChunk]:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [self._to_openai_msg(m) for m in messages],
            **self._extra_body,  # 供应商特定参（thinking 开关等）
            "stream": True,
            "stream_options": {"include_usage": True},
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
            required = [tool for tool in tools if tool.required]
            if len(required) > 1:
                raise ValueError("only one required text LLM tool is supported")
            payload["tool_choice"] = (
                {
                    "type": "function",
                    "function": {"name": required[0].name},
                }
                if required
                else "auto"
            )
        headers = {"Authorization": f"Bearer {self._api_key}"}
        url = f"{self._base_url}/chat/completions"
        # index -> {"id", "name", "args"}：工具调用参数按 index 跨 chunk 拼接
        acc: dict[int, dict[str, str]] = {}
        usage: ModelUsage | None = None
        usage_diagnostic: str | None = None
        call_id = await self._recorder.start(
            context=context,
            provider="openai_compat_text",
            model=self._model,
            attempt_no=1,
        )
        try:
            async for line in self._iter_lines(url, payload, headers):
                if not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                if data == "[DONE]":
                    break
                body = self._body(data)
                if body is None:
                    continue
                if "usage" in body:
                    usage, usage_diagnostic = self._usage_of(body["usage"])
                delta = self._delta(body)
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
            calls = self._tool_calls(acc)
        except asyncio.CancelledError:
            await self._recorder.interrupt(call_id)
            raise
        except GeneratorExit:
            await self._recorder.interrupt(call_id)
            raise
        except _UpstreamResponseError as exc:
            await self._recorder.fail(
                call_id,
                code="provider_error",
                detail=str(exc),
            )
            raise
        except TextLLMError as exc:
            await self._recorder.fail(
                call_id,
                code="invalid_response",
                detail=str(exc),
            )
            raise
        except httpx.HTTPError as exc:
            await self._recorder.fail(
                call_id,
                code="transport_error",
                detail=str(exc),
            )
            raise TextLLMError(f"文本 LLM 传输错误：{exc}") from exc
        await self._recorder.succeed(
            call_id,
            usage=usage or ModelUsage(),
            provider_request_id=None,
            platform_cost=None,
            diagnostic_code=(
                usage_diagnostic
                if usage is not None
                else "usage_missing"
            ),
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
        raise _UpstreamResponseError(
            f"文本 LLM {resp.status_code}: {resp.reason_phrase}"
        )

    @staticmethod
    def _body(data: str) -> dict[str, Any] | None:
        try:
            body = json.loads(data)
        except json.JSONDecodeError:
            return None
        return body if isinstance(body, dict) else None

    @staticmethod
    def _delta(body: dict[str, Any]) -> dict[str, Any] | None:
        choices = body.get("choices") or []
        if not choices:
            return None
        delta = choices[0].get("delta")
        return delta if isinstance(delta, dict) else None

    @classmethod
    def _usage_of(cls, raw: object) -> tuple[ModelUsage, str | None]:
        if not isinstance(raw, dict):
            return ModelUsage(), "usage_invalid"
        input_tokens, invalid_input = cls._token_value(
            raw.get("prompt_tokens")
        )
        output_tokens, invalid_output = cls._token_value(
            raw.get("completion_tokens")
        )
        total_tokens, invalid_total = cls._token_value(
            raw.get("total_tokens")
        )
        diagnostic = (
            "usage_invalid"
            if (
                invalid_input
                or invalid_output
                or invalid_total
                or (
                    input_tokens is None
                    and output_tokens is None
                    and total_tokens is None
                )
            )
            else None
        )
        return (
            ModelUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
            ),
            diagnostic,
        )

    @staticmethod
    def _token_value(value: object) -> tuple[int | None, bool]:
        if value is None:
            return None, False
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value, False
        return None, True

    def _tool_calls(
        self, acc: dict[int, dict[str, str]]
    ) -> tuple[ToolCall, ...]:
        return tuple(
            ToolCall(
                id=slot["id"] or slot["name"],
                name=slot["name"],
                arguments=self._parse_args(slot["args"]),
            )
            for _, slot in sorted(acc.items())
            if slot["name"]
        )

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
        content: str | list[dict[str, Any]]
        if m.images:
            if m.role != "user":
                raise ValueError("only user messages may include images")
            content = [{"type": "text", "text": m.content}]
            content.extend(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": (
                            f"data:{image.media_type};base64,"
                            f"{base64.b64encode(image.data).decode('ascii')}"
                        )
                    },
                }
                for image in m.images
            )
        else:
            content = m.content
        msg: dict[str, Any] = {"role": m.role, "content": content}
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
