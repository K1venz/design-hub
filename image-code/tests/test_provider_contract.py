"""provider 上游契约核（ISSUE-0045：返回张数 != 请求 n 必须 fail-fast，防双计费资损）。"""

import asyncio
from decimal import Decimal
from typing import Any

import httpx
import pytest

from design_hub.domain.enums import ModelName
from design_hub.domain.models import ReferenceImage
from design_hub.infrastructure.providers.api_key_pool import ApiKeyPool
from design_hub.infrastructure.providers.openai_compat import OpenAICompatImageProvider
from design_hub.ports.model_provider import ProviderError


def _provider() -> OpenAICompatImageProvider:
    return OpenAICompatImageProvider(
        name=ModelName.GPT_IMAGE_2,
        unit_cost=Decimal("0.40"),
        base_url="https://example.invalid",
        key_pool=ApiKeyPool(("k",)),
        model="gpt-image-2",
    )


class _CapturingClient:
    """假 httpx client：记录最后一次 POST 的 json/data 载荷，恒返 200（断言请求参数用）。"""

    def __init__(self, statuses: list[int] | None = None) -> None:
        self._statuses = list(statuses or [200])
        self.urls: list[str] = []
        self.headers: list[dict[str, str]] = []
        self.json_payload: dict[str, Any] | None = None
        self.data_payload: dict[str, Any] | None = None
        self.files_payload: list[tuple[str, tuple[str, bytes, str]]] | None = None

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        self.urls.append(url)
        self.headers.append(kwargs.get("headers", {}))
        self.json_payload = kwargs.get("json")
        self.data_payload = kwargs.get("data")
        self.files_payload = kwargs.get("files")
        status = self._statuses.pop(0) if len(self._statuses) > 1 else self._statuses[0]
        return httpx.Response(status, json={"data": [{"url": "https://x/1.png"}]})


class _Concurrent429Client:
    def __init__(self) -> None:
        self._both_started = asyncio.Event()
        self._request_a_retried = asyncio.Event()
        self.headers_by_prompt: dict[str, list[str]] = {}

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        payload = kwargs.get("json") or kwargs.get("data")
        prompt = str(payload["prompt"]).split("【本次生图要求】\n\n", 1)[1]
        authorization = str(kwargs["headers"]["Authorization"])
        attempts = self.headers_by_prompt.setdefault(prompt, [])
        attempts.append(authorization)
        if len(attempts) == 1:
            if prompt == "request-a":
                await self._both_started.wait()
            else:
                self._both_started.set()
                await self._request_a_retried.wait()
            return httpx.Response(429, json={"error": {"message": "rate limited"}})
        if prompt == "request-a":
            self._request_a_retried.set()
        return httpx.Response(200, json={"data": [{"url": "https://x/1.png"}]})


def _provider_with(client: object, **kw: Any) -> OpenAICompatImageProvider:
    key_pool = kw.pop("key_pool", ApiKeyPool(("k",)))
    return OpenAICompatImageProvider(
        name=ModelName.GPT_IMAGE_2, unit_cost=Decimal("0.40"),
        base_url="https://example.invalid/v1", key_pool=key_pool, model="gpt-image-2",
        client=client, **kw,  # type: ignore[arg-type]
    )


async def _run(provider: OpenAICompatImageProvider, *, refs: list[bytes]) -> None:
    await _run_prompt(provider, prompt="p", refs=refs)


async def _run_prompt(
    provider: OpenAICompatImageProvider,
    *,
    prompt: str,
    refs: list[bytes],
    negative_prompt: str = "",
) -> None:
    await provider.generate(
        prompt=prompt, negative_prompt=negative_prompt,
        reference_images=[ReferenceImage(data=b) for b in refs], size=(1024, 1024), n=1,
    )


# ── 出图协议增强（apinebula 文档，coordinator #1092）：input_fidelity + response_format ──


def test_edits_sends_input_fidelity_and_response_format() -> None:
    # edits 端点（有参考图）：两参数都发——input_fidelity 保真 + b64 自包含返回
    client = _CapturingClient()
    provider = _provider_with(client, input_fidelity="high", response_format="b64_json")
    asyncio.run(_run(provider, refs=[b"img"]))
    assert client.data_payload is not None
    assert client.data_payload["input_fidelity"] == "high"
    assert client.data_payload["response_format"] == "b64_json"


def test_edits_repeats_documented_image_field_for_multiple_references() -> None:
    client = _CapturingClient()
    provider = _provider_with(client)

    asyncio.run(_run(provider, refs=[b"product", b"background"]))

    assert client.urls == ["https://example.invalid/v1/images/edits"]
    assert client.files_payload is not None
    assert [field for field, _file in client.files_payload] == ["image", "image"]


def test_generations_sends_response_format_but_not_input_fidelity() -> None:
    # generations 端点（无参考图）：只发 response_format；input_fidelity 该端点无此参数、不发
    client = _CapturingClient()
    provider = _provider_with(client, input_fidelity="high", response_format="b64_json")
    asyncio.run(_run(provider, refs=[]))
    assert client.json_payload is not None
    assert client.json_payload["response_format"] == "b64_json"
    assert "input_fidelity" not in client.json_payload


@pytest.mark.parametrize("refs", [[], [b"product"]])
def test_final_image_payload_injects_policy_once_before_task_and_negative(
    refs: list[bytes],
) -> None:
    client = _CapturingClient()
    provider = _provider_with(client)

    asyncio.run(
        _run_prompt(
            provider,
            prompt="生成红色水杯",
            negative_prompt="不要水印",
            refs=refs,
        )
    )

    payload = client.data_payload if refs else client.json_payload
    assert payload is not None
    prompt = str(payload["prompt"])
    assert prompt.count("【全局真实性与细节质量约束】") == 1
    assert prompt.count("生成红色水杯") == 1
    assert prompt.index("生成红色水杯") < prompt.index("【需要避免】")
    assert prompt.endswith("不要水印")


def test_requests_round_robin_across_configured_api_keys() -> None:
    client = _CapturingClient()
    provider = _provider_with(client, key_pool=ApiKeyPool(("first-key", "second-key")))

    asyncio.run(_run(provider, refs=[]))
    asyncio.run(_run(provider, refs=[]))

    assert [headers["Authorization"] for headers in client.headers] == [
        "Bearer first-key",
        "Bearer second-key",
    ]


def test_retry_switches_to_next_api_key() -> None:
    client = _CapturingClient([429, 200])
    provider = _provider_with(
        client,
        key_pool=ApiKeyPool(("first-key", "second-key")),
        max_retries=1,
        retry_backoff=0.0,
        retry_max_sleep=0.0,
    )

    asyncio.run(_run(provider, refs=[]))

    assert [headers["Authorization"] for headers in client.headers] == [
        "Bearer first-key",
        "Bearer second-key",
    ]


def test_concurrent_retries_each_switch_away_from_its_starting_key() -> None:
    client = _Concurrent429Client()
    provider = _provider_with(
        client,
        key_pool=ApiKeyPool(("first-key", "second-key")),
        max_retries=1,
        retry_backoff=0.0,
        retry_max_sleep=0.0,
    )

    async def _impl() -> None:
        await asyncio.gather(
            _run_prompt(provider, prompt="request-a", refs=[]),
            _run_prompt(provider, prompt="request-b", refs=[]),
        )

    asyncio.run(_impl())

    assert client.headers_by_prompt == {
        "request-a": ["Bearer first-key", "Bearer second-key"],
        "request-b": ["Bearer second-key", "Bearer first-key"],
    }


def test_shared_pool_distributes_new_requests_across_providers() -> None:
    """共享池游标错误地留在各 Provider 内部时，此用例会失败。"""
    pool = ApiKeyPool(("key-a", "key-b", "key-c"))

    first = pool.reserve()
    second = pool.reserve()

    assert pool.key_for(first, 0) == "key-a"
    assert pool.key_for(second, 0) == "key-b"
    assert pool.key_for(first, 1) == "key-b"


def test_api_key_pool_rejects_empty_keys() -> None:
    with pytest.raises(ValueError, match="API key"):
        ApiKeyPool(())


def test_api_key_pool_repr_does_not_expose_secrets() -> None:
    pool = ApiKeyPool(("secret-a", "secret-b"))

    assert "secret-a" not in repr(pool)
    assert "secret-b" not in repr(pool)


def test_empty_config_sends_neither_param() -> None:
    # 空串=不发（保 CI/旧测行为，也是坏参可经 env 关的逃生阀）
    client = _CapturingClient()
    provider = _provider_with(client)  # 默认空
    asyncio.run(_run(provider, refs=[b"img"]))
    assert client.data_payload is not None
    assert "input_fidelity" not in client.data_payload
    assert "response_format" not in client.data_payload


def test_parse_over_deliver_truncates_and_bills_n() -> None:
    # 中转站对 n=1 回 2 条 data（ISSUE-0045 二修）：取前 1 张、计 1 份、不失败
    # ——出图保住（#735 用户实测：图是好的）+ 资损堵死（成本=n×unit 不随实返放大）
    body = {"data": [{"url": "https://x/1.png"}, {"url": "https://x/2.png"}]}
    images = asyncio.run(_provider()._parse(body, 0, 1, expected_n=1))
    assert len(images) == 1
    assert images[0].url == "https://x/1.png"  # 取前 n 张（保序）
    assert images[0].cost == Decimal("0.40")  # 计 n 份不计 len 份


def test_parse_under_deliver_fails() -> None:
    # 真缺图才失败（n=2 只回 1 张）；文案面向用户
    body = {"data": [{"url": "https://x/1.png"}]}
    with pytest.raises(ProviderError, match="出图数量不足"):
        asyncio.run(_provider()._parse(body, 0, 1, expected_n=2))


def test_parse_accepts_exact_count() -> None:
    body = {"data": [{"url": "https://x/1.png"}]}
    images = asyncio.run(_provider()._parse(body, 0, 1, expected_n=1))
    assert len(images) == 1
    assert images[0].cost == Decimal("0.40")  # 按张计费：恰 1 张恰 1 份
