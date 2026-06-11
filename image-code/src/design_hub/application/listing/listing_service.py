import asyncio
from dataclasses import dataclass, replace
from decimal import Decimal

from design_hub.application.cost.guard import CostGuard
from design_hub.application.listing.prompt_composer import (
    IMAGE_TYPES,
    CategoryCardRegistry,
    CloneModeRegistry,
    EditModeRegistry,
    ImageTypeRegistry,
    PromptModifierRegistry,
    compose_clone_prompt,
    compose_edit_prompt,
    compose_prompt,
)
from design_hub.application.listing.sizing import ratio_to_size
from design_hub.application.registry import ProviderRegistry
from design_hub.domain.enums import ModelName
from design_hub.domain.models import GeneratedImage, ListingResult
from design_hub.ports.model_provider import ProviderError

_MAX_IMAGES = 3
_MAX_N = 7  # 单图流张数上限（现行，不动）
_MIN_TOTAL = 3  # 套图总数下限（PRD §3.12.14，保「套」语义）
_MAX_TOTAL = 10  # 套图总数上限（gpt 实测批量上限内、单任务成本封顶）
_CONCURRENCY = 5  # 套图并发窗口（10 张超 n=7 实测包络，分批防上游限流）
_MAX_OVERLAY_TEXTS = 2
_MAX_OVERLAY_LEN = 12


def build_listing_prompts(
    prompt: str,
    modifiers: dict[str, str],
    modifier_registry: PromptModifierRegistry,
    card_registry: CategoryCardRegistry,
    type_registry: ImageTypeRegistry,
    *,
    category: str,
    n: int | None,
    plan: dict[str, int] | None,
    overlay_texts: tuple[str, ...] = (),
) -> list[tuple[str | None, str]]:
    """校验 + 展开为 [(图型|None, final_prompt)] 任务列表（路由 fail-fast 与编排共用，单一事实源）。

    单图流（n）：无图型卡块、overlay_texts 非法；套图（plan）：每图型独立组装、
    卖点按有无 overlay_texts 选块（PRD §3.12.14）。plan 与 n 显式互斥。
    """
    if (n is None) == (plan is None):
        raise ValueError("plan 与 n 互斥，需恰好带其一")
    if plan is None:
        assert n is not None
        if overlay_texts:
            raise ValueError("overlay_texts 仅套图（plan）含卖点图时合法")
        if not 1 <= n <= _MAX_N:
            raise ValueError(f"张数需为 1..{_MAX_N}，实际 {n}")
        final = compose_prompt(
            prompt, modifiers, modifier_registry,
            category=category, card_registry=card_registry,
        )
        return [(None, final)] * n
    unknown = set(plan) - set(IMAGE_TYPES)
    if unknown:
        raise ValueError(f"未知图型：{'、'.join(sorted(unknown))}（合法：{'/'.join(IMAGE_TYPES)}）")
    if any(v < 0 for v in plan.values()):
        raise ValueError("图型张数不能为负")
    total = sum(plan.values())
    if not _MIN_TOTAL <= total <= _MAX_TOTAL:
        raise ValueError(f"套图总数需为 {_MIN_TOTAL}..{_MAX_TOTAL}，实际 {total}")
    if overlay_texts:
        if plan.get("卖点", 0) <= 0:
            raise ValueError("overlay_texts 仅在 plan 含卖点图时合法")
        if len(overlay_texts) > _MAX_OVERLAY_TEXTS:
            raise ValueError(f"图上文案最多 {_MAX_OVERLAY_TEXTS} 条，实际 {len(overlay_texts)}")
        for t in overlay_texts:
            if not t.strip():
                raise ValueError("图上文案不能为空白")
            if len(t) > _MAX_OVERLAY_LEN:
                raise ValueError(f"图上文案每条最多 {_MAX_OVERLAY_LEN} 字：{t}")
    tasks: list[tuple[str | None, str]] = []
    for image_type in IMAGE_TYPES:  # 稳定序：白底 → 场景 → 卖点
        count = plan.get(image_type, 0)
        if count == 0:
            continue
        block = type_registry.block(
            image_type, overlay_texts if image_type == "卖点" else ()
        )
        final = compose_prompt(
            prompt, modifiers, modifier_registry,
            category=category, card_registry=card_registry, image_type_block=block,
        )
        tasks.extend([(image_type, final)] * count)
    return tasks


@dataclass
class ListingGenerationService:
    """listing 出图用例：组装 prompt → 守门预扣 → gpt-image-2 出图 → 回正。

    单图流（n）= n 个并发单图请求（现行，零破坏）；套图（plan）= 按图型展开后经
    并发窗口（Semaphore=_CONCURRENCY）分批出图，每张带图型标签、部分失败容错
    （≥1 成功即返回、failures 记图型+原因，对接 ISSUE-0030「部分完成」）。
    """

    registry: ProviderRegistry
    guard: CostGuard
    modifier_registry: PromptModifierRegistry
    card_registry: CategoryCardRegistry
    type_registry: ImageTypeRegistry
    clone_registry: CloneModeRegistry
    edit_registry: EditModeRegistry

    async def generate(
        self,
        *,
        prompt: str,
        modifiers: dict[str, str],
        images: tuple[bytes, ...],
        ratio: str,
        user_id: str,
        category: str,
        n: int | None = None,
        plan: dict[str, int] | None = None,
        overlay_texts: tuple[str, ...] = (),
    ) -> ListingResult:
        if not 1 <= len(images) <= _MAX_IMAGES:
            raise ValueError(f"参考图数量需为 1..{_MAX_IMAGES}，实际 {len(images)}")
        tasks = build_listing_prompts(
            prompt, modifiers, self.modifier_registry, self.card_registry,
            self.type_registry,
            category=category, n=n, plan=plan, overlay_texts=overlay_texts,
        )
        size = ratio_to_size(ratio)
        provider = self.registry.get(ModelName.GPT_IMAGE_2)
        estimate = provider.unit_cost * len(tasks)
        await self.guard.precheck_and_reserve(user_id, estimate)
        ref = list(images)
        # 卖点有字张走 high 档（宪章 §2.1 图上文字；prompt 卡建议、#491 知会 PM）
        overlay_quality = "high" if overlay_texts else None
        sem = asyncio.Semaphore(_CONCURRENCY)

        async def one(seed: int, image_type: str | None, final_prompt: str) -> list[GeneratedImage]:
            async with sem:
                quality = overlay_quality if image_type == "卖点" else None
                generated = await provider.generate(
                    prompt=final_prompt,
                    negative_prompt="",
                    reference_images=ref,
                    size=size,
                    n=1,
                    seed=seed,
                    quality=quality,
                )
                return [replace(im, image_type=image_type) for im in generated]

        coros = [one(i, t, p) for i, (t, p) in enumerate(tasks)]
        results = await asyncio.gather(*coros, return_exceptions=True)
        generated: list[GeneratedImage] = []
        failures: list[tuple[str, str]] = []
        first_error: BaseException | None = None
        for (image_type, _), r in zip(tasks, results, strict=True):
            if isinstance(r, BaseException):
                first_error = first_error or r
                if image_type is not None:  # 套图：失败张记图型+原因（SSE IMAGE_FAILED 用）
                    failures.append((image_type, str(r)))
            else:
                generated.extend(r)
        if not generated:
            await self.guard.rollback(user_id, estimate)
            raise first_error or ProviderError("listing 出图全部失败")
        total = sum((img.cost for img in generated), Decimal("0"))
        await self.guard.reconcile(user_id, reserved=estimate, actual=total)
        return ListingResult(
            prompt=tasks[0][1],  # 代表 prompt（首任务的 final_prompt；套图各图型块不同、取首个）
            used_model=ModelName.GPT_IMAGE_2,
            images=tuple(generated),
            total_cost=total,
            failures=tuple(failures),
        )

    async def clone(
        self,
        *,
        prompt: str,
        modifiers: dict[str, str],
        product_image: bytes,
        reference_images: tuple[bytes, ...],
        ratio: str,
        user_id: str,
        category: str,
        clone_mode: str,
    ) -> ListingResult:
        """爆款复刻（PRD §3.13）：单张 edit、喂图保序「产品前·参考后」（角色指认契约）。

        prompt 选填（空=合法，模板+产品图已承载语义）；档位/品类/下拉 fail-fast。
        复用 guard 预扣→回正/回滚（单张成败二元，无部分失败语义）。
        """
        if not 1 <= len(reference_images) <= 2:
            raise ValueError(f"爆款参考图需为 1..2 张，实际 {len(reference_images)}")
        final_prompt = compose_clone_prompt(
            prompt, modifiers, self.modifier_registry,
            category=category, card_registry=self.card_registry,
            clone_registry=self.clone_registry, clone_mode=clone_mode,
        )
        size = ratio_to_size(ratio)
        provider = self.registry.get(ModelName.GPT_IMAGE_2)
        estimate = provider.unit_cost  # 一次出 1 张
        await self.guard.precheck_and_reserve(user_id, estimate)
        try:
            generated = await provider.generate(
                prompt=final_prompt,
                negative_prompt="",
                reference_images=[product_image, *reference_images],  # 序=角色契约
                size=size,
                n=1,
                seed=0,
            )
        except Exception:
            await self.guard.rollback(user_id, estimate)
            raise
        total = sum((img.cost for img in generated), Decimal("0"))
        await self.guard.reconcile(user_id, reserved=estimate, actual=total)
        return ListingResult(
            prompt=final_prompt,
            used_model=ModelName.GPT_IMAGE_2,
            images=tuple(generated),
            total_cost=total,
        )

    async def edit(
        self,
        *,
        prompt: str,
        modifiers: dict[str, str],
        source_image: bytes,
        anchor_images: tuple[bytes, ...],
        ratio: str,
        user_id: str,
        edit_mode: str,
    ) -> ListingResult:
        """二次编辑（PRD §3.12.13/ISSUE-0040）：单张 edit、喂序「源图第 1·链根锚其后」。

        锚=迭代链根原始产品图 1..3 张（D2 命门：每轮从零失真事实源锚，漂移不随轮数
        叠加，绝不取上一轮产出）。指令必填（E-⑤）；modifiers=叠新后的 effective。
        复用 guard 预扣→回正/回滚（单张成败二元，同 clone）。
        """
        if not 1 <= len(anchor_images) <= 3:
            raise ValueError(f"链根产品锚需为 1..3 张，实际 {len(anchor_images)}")
        final_prompt = compose_edit_prompt(
            prompt, modifiers, self.modifier_registry,
            edit_registry=self.edit_registry, edit_mode=edit_mode,
        )
        size = ratio_to_size(ratio)
        provider = self.registry.get(ModelName.GPT_IMAGE_2)
        estimate = provider.unit_cost  # 一次出 1 张（Q-ε）
        await self.guard.precheck_and_reserve(user_id, estimate)
        try:
            generated = await provider.generate(
                prompt=final_prompt,
                negative_prompt="",
                reference_images=[source_image, *anchor_images],  # 序=角色契约（源图第 1）
                size=size,
                n=1,
                seed=0,
            )
        except Exception:
            await self.guard.rollback(user_id, estimate)
            raise
        total = sum((img.cost for img in generated), Decimal("0"))
        await self.guard.reconcile(user_id, reserved=estimate, actual=total)
        return ListingResult(
            prompt=final_prompt,
            used_model=ModelName.GPT_IMAGE_2,
            images=tuple(generated),
            total_cost=total,
        )
