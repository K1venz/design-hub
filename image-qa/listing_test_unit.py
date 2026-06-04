"""ISSUE-0023 Layer1 纯单元：listing prompt_composer / sizing / service（无 DB，Mock provider）。

cd image-code && uv run python ../image-qa/listing_test_unit.py
"""

import asyncio
from decimal import Decimal

from design_hub.application.cost.budget import BudgetPolicy
from design_hub.application.cost.guard import CostGuard
from design_hub.application.listing.listing_service import ListingGenerationService
from design_hub.application.listing.prompt_composer import (
    PromptModifierRegistry,
    compose_prompt,
)
from design_hub.application.listing.sizing import ratio_to_size
from design_hub.application.registry import ProviderRegistry
from design_hub.domain.enums import ModelName
from design_hub.domain.errors import DomainError
from design_hub.infrastructure.ledger.memory import InMemoryLedgerRepository
from design_hub.infrastructure.providers.mock import MockModelProvider

R: list[tuple[str, bool]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    R.append((name, bool(cond)))
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")


def expect_domain(name: str, fn) -> None:  # noqa: ANN001
    try:
        fn()
        check(name, False, "(未抛错)")
    except DomainError as e:
        check(name, True, f"-> DomainError: {e}")
    except Exception as e:  # noqa: BLE001
        check(name, False, f"(错误类型 {type(e).__name__}: {e})")


def unit_sync() -> None:
    reg = PromptModifierRegistry()
    # 用例11 compose_prompt
    p = compose_prompt("纯白背景突出产品质感", {"platform": "亚马逊", "region": "美国", "language": "英文"}, reg)
    check("11.compose 含用户自由文本", "纯白背景突出产品质感" in p, repr(p))
    check("11.compose 含各 modifier 片段", all(s in p for s in ["亚马逊", "美国市场", "英文"]))
    check("11.compose 用户文本在最前 + 。；分隔", p.startswith("纯白背景突出产品质感。") and "；" in p)
    check("11.compose 无 modifier 仅 base", compose_prompt("只有正文", {}, reg) == "只有正文")
    expect_domain("11.compose 空 prompt→DomainError", lambda: compose_prompt("   ", {"platform": "亚马逊"}, reg))
    # 用例5 未知下拉值
    expect_domain("5.未知 value→DomainError", lambda: reg.fragment("platform", "不存在平台"))
    expect_domain("5.未知 field→DomainError", lambda: reg.fragment("foo", "bar"))
    check("5.已知值→正确片段", reg.fragment("platform", "京东") == "用于京东电商平台的商品展示图")

    # 用例12 ratio_to_size
    check("12.1:1→1024²", ratio_to_size("1:1") == (1024, 1024))
    check("12.3:4→1024×1536", ratio_to_size("3:4") == (1024, 1536))
    check("12.9:16→1024×1536", ratio_to_size("9:16") == (1024, 1536))
    check("12.16:9→1536×1024", ratio_to_size("16:9") == (1536, 1024))
    expect_domain("6.非法 ratio(2:1)→DomainError", lambda: ratio_to_size("2:1"))
    check("注:4:3 也被接受(超出 ISSUE-0021 确认集 1:1/3:4/9:16/16:9)", ratio_to_size("4:3") == (1536, 1024))


def mk_registry(fail: bool = False) -> ProviderRegistry:
    r = ProviderRegistry()
    r.register(MockModelProvider(name=ModelName.GPT_IMAGE_2, unit_cost=Decimal("1.19"), fail=fail))
    return r


async def unit_service() -> None:
    led = InMemoryLedgerRepository()
    svc = ListingGenerationService(
        registry=mk_registry(), guard=CostGuard(ledger=led, policy=BudgetPolicy()),
        modifier_registry=PromptModifierRegistry(),
    )
    res = await svc.generate(prompt="正文", modifiers={"platform": "亚马逊"}, images=(b"x",), ratio="1:1", n=3, user_id="u1")
    check("service 出 n=3 张 + used_model=gpt-image-2", len(res.images) == 3 and res.used_model == ModelName.GPT_IMAGE_2)
    net = (await led.snapshot("u1")).user_month_used
    check("13.成本=1.19×3=3.57 且 ledger 回正一致", res.total_cost == Decimal("3.57") and net == Decimal("3.57"), f"total={res.total_cost} net={net}")

    # n / 图数 越界（service 层 fail-fast）
    for bad in (0, 8, -1):
        try:
            await svc.generate(prompt="正文", modifiers={}, images=(b"x",), ratio="1:1", n=bad, user_id="ux")
            check(f"3.service n={bad}→DomainError", False, "(未抛)")
        except DomainError:
            check(f"3.service n={bad}→DomainError", True)
    for imgs in ((), (b"a", b"b", b"c", b"d")):
        try:
            await svc.generate(prompt="正文", modifiers={}, images=imgs, ratio="1:1", n=1, user_id="uy")
            check(f"2.service 图数={len(imgs)}→DomainError", False, "(未抛)")
        except DomainError:
            check(f"2.service 图数={len(imgs)}→DomainError", True)

    # 用例13 provider 失败 → 预扣回滚（额度不漏）
    led2 = InMemoryLedgerRepository()
    svc_f = ListingGenerationService(
        registry=mk_registry(fail=True), guard=CostGuard(ledger=led2, policy=BudgetPolicy()),
        modifier_registry=PromptModifierRegistry(),
    )
    try:
        await svc_f.generate(prompt="正文", modifiers={}, images=(b"x",), ratio="1:1", n=2, user_id="u4")
        check("13.provider 失败→上抛", False, "(未抛)")
    except Exception as e:  # noqa: BLE001
        net = (await led2.snapshot("u4")).user_month_used
        check("13.失败后预扣回滚 净额=0", net == Decimal("0"), f"net={net} exc={type(e).__name__}")


def main() -> None:
    unit_sync()
    asyncio.run(unit_service())
    n = sum(1 for _, c in R if c)
    print(f"\n==== UNIT: {n}/{len(R)} passed ====")


main()
