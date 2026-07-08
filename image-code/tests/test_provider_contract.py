"""provider 上游契约核（ISSUE-0045：返回张数 != 请求 n 必须 fail-fast，防双计费资损）。"""

import asyncio
from decimal import Decimal
from typing import Any

import httpx
import pytest

from design_hub.domain.enums import ModelName
from design_hub.domain.models import ReferenceImage
from design_hub.infrastructure.providers.openai_compat import OpenAICompatImageProvider
from design_hub.ports.model_provider import ProviderError


def _provider() -> OpenAICompatImageProvider:
    return OpenAICompatImageProvider(
        name=ModelName.GPT_IMAGE_2,
        unit_cost=Decimal("0.40"),
        base_url="https://example.invalid",
        api_keys=["k"],
        model="gpt-image-2",
    )


class _CapturingClient:
    """假 httpx client：记录最后一次 POST 的 json/data 载荷，恒返 200（断言请求参数用）。"""

    def __init__(self) -> None:
        self.json_payload: dict[str, Any] | None = None
        self.data_payload: dict[str, Any] | None = None

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        self.json_payload = kwargs.get("json")
        self.data_payload = kwargs.get("data")
        return httpx.Response(200, json={"data": [{"url": "https://x/1.png"}]})


def _provider_with(client: _CapturingClient, **kw: Any) -> OpenAICompatImageProvider:
    return OpenAICompatImageProvider(
        name=ModelName.GPT_IMAGE_2, unit_cost=Decimal("0.40"),
        base_url="https://example.invalid", api_keys=["k"], model="gpt-image-2",
        client=client, **kw,  # type: ignore[arg-type]
    )


async def _run(provider: OpenAICompatImageProvider, *, refs: list[bytes]) -> None:
    await provider.generate(
        prompt="p", negative_prompt="",
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


def test_generations_sends_response_format_but_not_input_fidelity() -> None:
    # generations 端点（无参考图）：只发 response_format；input_fidelity 该端点无此参数、不发
    client = _CapturingClient()
    provider = _provider_with(client, input_fidelity="high", response_format="b64_json")
    asyncio.run(_run(provider, refs=[]))
    assert client.json_payload is not None
    assert client.json_payload["response_format"] == "b64_json"
    assert "input_fidelity" not in client.json_payload


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
