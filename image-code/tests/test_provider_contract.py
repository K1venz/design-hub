"""provider 上游契约核（ISSUE-0045：返回张数 != 请求 n 必须 fail-fast，防双计费资损）。"""

import asyncio
from decimal import Decimal

import pytest

from design_hub.domain.enums import ModelName
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
