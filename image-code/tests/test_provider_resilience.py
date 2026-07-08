"""套图并发 429 韧性（ISSUE-0047）：provider 抖动重试 + service 并发上限。

单测用 mock（无真实上游）：只能证「逻辑正确」——真实 429 只能真出图压测（见 QA
taotu_concurrency_verify.py 多遍压并发）。此处锁两条契约：
  ① provider 对 429/瞬时网络错重试、对 4xx 业务错 fail-fast 不重试；
  ② 套图并发被 Semaphore 卡在 concurrency 上限内，单图流 n=1 恒 1 路不受影响。
"""

import asyncio
from decimal import Decimal

import httpx
import pytest

from design_hub.application.listing.listing_service import ListingGenerationService
from design_hub.application.listing.prompt_composer import (
    CategoryCardRegistry,
    CloneModeRegistry,
    EditModeRegistry,
    ImageTypeRegistry,
    PromptModifierRegistry,
)
from design_hub.application.registry import ProviderRegistry
from design_hub.domain.enums import ModelName
from design_hub.domain.errors import DomainError
from design_hub.domain.models import GeneratedImage, ReferenceImage
from design_hub.infrastructure.providers.openai_compat import OpenAICompatImageProvider
from design_hub.ports.model_provider import ProviderTimeout

# --------------------------------------------------------------------------- #
# provider 重试 / 抖动退避（4xx fail-fast、429/瞬时网络错重试）
# --------------------------------------------------------------------------- #


class _SequencedClient:
    """假 httpx client：每次 POST 弹出一个预排 Response，或抛一个预排异常。"""

    def __init__(self, outcomes: list[object]) -> None:
        self._outcomes = list(outcomes)
        self.calls = 0

    async def post(self, *args: object, **kwargs: object) -> httpx.Response:
        self.calls += 1
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        assert isinstance(outcome, httpx.Response)
        return outcome


def _provider(
    client: _SequencedClient, *, max_retries: int, retry_max_elapsed: float = 90.0
) -> OpenAICompatImageProvider:
    # 退避设极小值，单测不真等；契约不依赖具体时长
    return OpenAICompatImageProvider(
        name=ModelName.GPT_IMAGE_2,
        unit_cost=Decimal("0.40"),
        base_url="https://example.invalid",
        api_keys=["k"],
        model="gpt-image-2",
        client=client,  # type: ignore[arg-type]
        max_retries=max_retries,
        retry_backoff=0.001,
        retry_max_sleep=0.005,
        retry_max_elapsed=retry_max_elapsed,
    )


def _ok() -> httpx.Response:
    return httpx.Response(200, json={"data": [{"url": "https://x/1.png"}]})


def _429() -> httpx.Response:
    return httpx.Response(429, text="rate limited")


def _500() -> httpx.Response:
    return httpx.Response(500, text="prepare chat requirements error")


async def _gen(provider: OpenAICompatImageProvider) -> list[GeneratedImage]:
    return await provider.generate(
        prompt="p", negative_prompt="",
        reference_images=[ReferenceImage(data=b"img")], size=(1024, 1024), n=1,
    )


def test_generate_retries_on_429_then_succeeds() -> None:
    # 套图核心场景：并发撞 429 后退避重试即成——不再「只出 1 张」
    client = _SequencedClient([_429(), _429(), _ok()])
    images = asyncio.run(_gen(_provider(client, max_retries=5)))
    assert len(images) == 1
    assert client.calls == 3  # 2 次 429 重试 + 第 3 次成功


def test_generate_exhausts_retry_budget_and_raises() -> None:
    # 预算耗尽仍 429 → 抛 ProviderTimeout（I/O 域穷尽后如实上抛，不静默）
    client = _SequencedClient([_429(), _429(), _429(), _429()])
    with pytest.raises(ProviderTimeout):
        asyncio.run(_gen(_provider(client, max_retries=3)))
    assert client.calls == 4  # 首发 + 3 次重试


def test_wall_clock_budget_stops_persistent_5xx_despite_max_retries() -> None:
    # ISSUE-0055 (i)：总重试墙钟耗尽即穷尽 fail-closed——持久 5xx 不再干等 max_retries×退避。
    # 预算=0 → 首次失败后墙钟即耗尽、绝不重试（尽管 max_retries=5 本可 6 次调用）。
    client = _SequencedClient([_500(), _500(), _500(), _500(), _500(), _500()])
    with pytest.raises(ProviderTimeout):
        asyncio.run(_gen(_provider(client, max_retries=5, retry_max_elapsed=0.0)))
    assert client.calls == 1  # 墙钟预算截断，非 max_retries（否则会 6 次）


def test_generate_does_not_retry_4xx_business_error() -> None:
    # 4xx 坏请求/鉴权是业务错 → fail-fast 立抛 DomainError，绝不重试
    client = _SequencedClient([httpx.Response(400, text="bad request")])
    with pytest.raises(DomainError):
        asyncio.run(_gen(_provider(client, max_retries=5)))
    assert client.calls == 1  # 无重试


def test_generate_retries_transient_network_error() -> None:
    # 连接层瞬时错（I/O 域）也重试
    client = _SequencedClient([httpx.ConnectError("boom"), _ok()])
    images = asyncio.run(_gen(_provider(client, max_retries=2)))
    assert len(images) == 1
    assert client.calls == 2


def test_retry_sleep_exponential_bounded_and_jittered() -> None:
    provider = OpenAICompatImageProvider(
        name=ModelName.GPT_IMAGE_2,
        unit_cost=Decimal("0.40"),
        base_url="https://example.invalid",
        api_keys=["k"],
        model="gpt-image-2",
        retry_backoff=2.0,
        retry_max_sleep=30.0,
    )
    seen: set[float] = set()
    for attempt in range(1, 8):
        backoff = min(30.0, 2.0 * 2 ** (attempt - 1))
        sleep = provider._retry_sleep(attempt)
        assert backoff / 2 <= sleep <= backoff  # equal-jitter 上下界
        assert sleep <= 30.0  # 封顶
        seen.add(round(sleep, 6))
    assert len(seen) > 1  # 抖动确有随机、非定值（错峰去相关）


# --------------------------------------------------------------------------- #
# service 套图并发上限（Semaphore）+ 单图流不回归
# --------------------------------------------------------------------------- #


class _NoopGuard:
    """成本守卫替身：预扣/回正/回滚全 no-op（并发契约与成本无关）。"""

    async def precheck_and_reserve(self, user_id: str, estimate: Decimal) -> None: ...
    async def rollback(self, user_id: str, estimate: Decimal) -> None: ...
    async def reconcile(self, user_id: str, *, reserved: Decimal, actual: Decimal) -> None: ...


class _ConcurrencyProbeProvider:
    """记录峰值在飞数的 provider 替身：出图时 sleep 撑开重叠，便于观测真实并发度。"""

    name = ModelName.GPT_IMAGE_2
    unit_cost = Decimal("0.40")
    is_live = True

    def __init__(self) -> None:
        self.inflight = 0
        self.max_inflight = 0

    async def generate(
        self, *, prompt: str, negative_prompt: str, reference_images: list[ReferenceImage],
        size: tuple[int, int], n: int, seed: int | None = None, quality: str | None = None,
    ) -> list[GeneratedImage]:
        self.inflight += 1
        self.max_inflight = max(self.max_inflight, self.inflight)
        try:
            await asyncio.sleep(0.02)  # 持槽，令并发重叠可观测
        finally:
            self.inflight -= 1
        return [
            GeneratedImage(
                url=f"mock://{seed}.png", seed=seed or 0, latency_ms=1, cost=self.unit_cost
            )
        ]


def _service(concurrency: int) -> tuple[ListingGenerationService, _ConcurrencyProbeProvider]:
    provider = _ConcurrencyProbeProvider()
    registry = ProviderRegistry()
    registry.register(provider)  # type: ignore[arg-type]
    service = ListingGenerationService(
        registry=registry,
        guard=_NoopGuard(),  # type: ignore[arg-type]
        modifier_registry=PromptModifierRegistry(),
        card_registry=CategoryCardRegistry(),
        type_registry=ImageTypeRegistry(),
        clone_registry=CloneModeRegistry(),
        edit_registry=EditModeRegistry(),
        concurrency=concurrency,
    )
    return service, provider


_MODS = {"platform": "淘宝天猫1688", "language": "中文"}


def test_set_generation_never_exceeds_concurrency() -> None:
    # 10 张套图压并发：全出、峰值在飞 ≤ concurrency（降并发生效，不再打满上游）
    service, provider = _service(concurrency=3)
    result = asyncio.run(
        service.generate(
            prompt="春节红色背景", modifiers=_MODS, images=(b"x",), ratio="1:1",
            user_id="u1", category="FOOD",
            plan={"白底": 3, "场景": 4, "卖点": 3}, overlay_texts=("高山七彩花生",),
        )
    )
    assert len(result.images) == 10  # 全套出全
    assert provider.max_inflight <= 3  # 并发不超上限
    assert provider.max_inflight >= 2  # 确有并发（未退化成串行）


def test_single_image_flow_one_inflight_regardless_of_cap() -> None:
    # 单图流 n=1 恒 1 路：任何并发档都不改其行为（ISSUE-0047 不回归单图）
    service, provider = _service(concurrency=2)
    result = asyncio.run(
        service.generate(
            prompt="干净背景主图", modifiers=_MODS, images=(b"x",), ratio="1:1",
            user_id="u1", category="FOOD", n=1,
        )
    )
    assert len(result.images) == 1
    assert provider.max_inflight == 1


def test_concurrency_below_one_fails_fast() -> None:
    # 配置校验 fail-fast：并发档 <1 是配置错，构造即抛
    with pytest.raises(ValueError):
        _service(concurrency=0)
