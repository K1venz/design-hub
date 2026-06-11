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


def test_parse_rejects_count_mismatch() -> None:
    # 中转站对 n=1 回 2 条 data → 必须拒，不得落 2 图计 2 份（ISSUE-0045 现象）
    body = {"data": [{"url": "https://x/1.png"}, {"url": "https://x/2.png"}]}
    with pytest.raises(ProviderError):
        asyncio.run(_provider()._parse(body, 0, 1, expected_n=1))


def test_parse_accepts_exact_count() -> None:
    body = {"data": [{"url": "https://x/1.png"}]}
    images = asyncio.run(_provider()._parse(body, 0, 1, expected_n=1))
    assert len(images) == 1
    assert images[0].cost == Decimal("0.40")  # 按张计费：恰 1 张恰 1 份
