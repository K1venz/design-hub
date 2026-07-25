import logging
from abc import abstractmethod
from dataclasses import dataclass
from decimal import Decimal

from design_hub.application.listing.error_messages import humanize_image_error
from design_hub.application.listing.listing_service import ListingGenerationService
from design_hub.application.listing.sizing import ratio_to_size
from design_hub.domain.enums import TaskEventType
from design_hub.domain.media import image_key_from_url
from design_hub.domain.models import (
    ListingJobImage,
    ListingJobStart,
    ListingResult,
    ReferenceImage,
    TaskEvent,
)
from design_hub.ports.events import EventPublisher
from design_hub.ports.listing_history import ListingHistory
from design_hub.ports.task_queue import GenerationCommand

logger = logging.getLogger(__name__)

# 失败张（套图部分完成）无产物：image_key 空串占位、seed 哨兵；读侧按 status 区分、不签 url。
_FAILED_IMAGE_KEY = ""
_FAILED_SEED = -1


def _failure_summary(failures: tuple[tuple[str, str], ...]) -> str:
    """套图部分失败摘要（图型：原因），落 listing_job.error（既有列，无 per-image 原因列）。"""
    return "；".join(f"{image_type}：{error}" for image_type, error in failures)


@dataclass
class ListingCommand(GenerationCommand):
    """listing 异步命令基类（两阶段落库 ISSUE-0047）：入队建行→出图→落图→终态，全程 fail-closed。

    模板方法：run() 固化「建行→TASK_STARTED→出图→落库/发事件→终态→TASK_COMPLETED」骨架
    与两处 fail-closed 守卫（出图段、落库/发事件段），任一失败都先 finalize('失败')+TASK_FAILED
    再 raise——绝不留永久「生成中」僵尸行、绝不 SSE 永久转圈。子类只填 _start（建行快照）与
    _generate（具体 service 调用）。成本 reserve/reconcile/rollback 在 service 内自洽，本层不碰。
    """

    service: ListingGenerationService
    events: EventPublisher
    history: ListingHistory
    user_id: str
    prompt: str
    modifiers: dict[str, str]
    ratio: str

    @abstractmethod
    def _start(self, job_id: str, size: str) -> ListingJobStart:
        """入队建行快照（status='生成中'）：job 元数据 + 输入产品图。"""
        ...

    @abstractmethod
    async def _generate(self) -> ListingResult:
        """调用具体 service 用例出图（成本预扣/回正/回滚均在 service 内）。"""
        ...

    def _requested(self) -> int:
        """请求总张数（状态判定用）：单张流（复刻/编辑）恒 1；套图/单图流覆写。"""
        return 1

    async def run(self, job_id: str) -> None:
        size = "{}x{}".format(*ratio_to_size(self.ratio))
        await self.history.start(self._start(job_id, size))  # 入队建行：status='生成中'
        await self.events.publish(TaskEvent(job_id, TaskEventType.TASK_STARTED, {}))
        try:
            result = await self._generate()
        except Exception as exc:  # 出图段兜底：成本已在 service 内回滚/未预扣 → 本单未扣费
            await self._fail(job_id, exc, refunded=True)
            raise
        try:
            # fail-closed（Finding A）：出图成功后的「发事件/落图/终态」段裸奔会留永久
            # 「生成中」僵尸行 + SSE 永久转圈，故整段兜底——同 generate 段同构。
            await self._persist_and_complete(job_id, result)
        except Exception as exc:  # 落库段：出图已成功且已计费 → 不宣称未扣费
            await self._fail(job_id, exc, refunded=False)
            raise

    async def _persist_and_complete(self, job_id: str, result: ListingResult) -> None:
        await self.events.publish(
            TaskEvent(job_id, TaskEventType.MODEL_CALLED, {"model": result.used_model.value})
        )
        for image in result.images:
            await self.events.publish(
                TaskEvent(
                    job_id,
                    TaskEventType.IMAGE_GENERATED,
                    {"url": image.url, "seed": image.seed, "image_type": image.image_type},
                )
            )
        for image_type, error in result.failures:  # 套图单张失败（SSE 即时可见）；单张流恒空
            await self.events.publish(
                TaskEvent(
                    job_id,
                    TaskEventType.IMAGE_FAILED,
                    {"image_type": image_type, "error": error},
                )
            )
        success_images = tuple(
            ListingJobImage(
                image_key=image_key_from_url(im.url),
                seed=im.seed,
                cost=im.cost,
                status="成功",
                image_type=im.image_type,
            )
            for im in result.images
        )
        failure_images = tuple(
            ListingJobImage(
                image_key=_FAILED_IMAGE_KEY,
                seed=_FAILED_SEED,
                cost=Decimal("0"),
                status="失败",
                image_type=image_type,
            )
            for image_type, _ in result.failures
        )
        await self.history.add_images(job_id, success_images + failure_images)
        status = "完成" if len(success_images) >= self._requested() else "部分完成"
        job_error = _failure_summary(result.failures) if result.failures else None
        await self.history.finalize(  # 终态提交先于 TASK_COMPLETED（前端据完成事件详情必 200）
            job_id, status=status, total_cost=result.total_cost, error=job_error
        )
        await self.events.publish(
            TaskEvent(
                job_id, TaskEventType.TASK_COMPLETED, {"total_cost": str(result.total_cost)}
            )
        )

    async def _fail(self, job_id: str, exc: Exception, *, refunded: bool) -> None:
        """失败兜底：finalize('失败') 先于 TASK_FAILED（时序契约）。finalize 本身失败即
        抛（DB 真 down 由启动 reaper 扫尾，Finding B），绝不静默吞。成本不动（service 内）。

        用户面错误话术化（ISSUE-0055 (ii)）：原始技术错进日志、落库/发事件用人话；
        refunded=True（出图段=已回滚/未预扣）附「本单未扣费」，落库段(已计费)不附。"""
        logger.warning("listing job %s failed: %r", job_id, exc)  # 原始技术错留观测、不进用户面
        user_error = humanize_image_error(exc)
        if refunded:
            user_error += "（本单未扣费）"
        await self.history.finalize(
            job_id, status="失败", total_cost=Decimal("0"), error=user_error
        )
        await self.events.publish(
            TaskEvent(job_id, TaskEventType.TASK_FAILED, {"error": user_error})
        )


@dataclass
class ListingGenerationCommand(ListingCommand):
    """listing 一键出图：单图流（n）或套图（plan）；套图失败张留痕、状态可「部分完成」。"""

    images: tuple[ReferenceImage, ...]
    upload_keys: tuple[str, ...]
    category: str | None
    n: int | None = None
    plan: dict[str, int] | None = None  # 套图配比（与 n 互斥，PRD §3.12.14）
    overlay_texts: tuple[str, ...] = ()

    async def _generate(self) -> ListingResult:
        return await self.service.generate(
            prompt=self.prompt,
            modifiers=self.modifiers,
            images=self.images,
            ratio=self.ratio,
            n=self.n,
            plan=self.plan,
            overlay_texts=self.overlay_texts,
            user_id=self.user_id,
            category=self.category,
        )

    def _requested(self) -> int:
        """请求总张数：单图流=n、套图=Σplan（历史 n 列与状态判定共用）。"""
        return self.n if self.n is not None else sum((self.plan or {}).values())

    def _start(self, job_id: str, size: str) -> ListingJobStart:
        return ListingJobStart(
            job_id=job_id,
            user_id=self.user_id,
            prompt=self.prompt,
            modifiers=self.modifiers,
            ratio=self.ratio,
            size=size,
            n=self._requested(),
            upload_keys=self.upload_keys,
            category=self.category,
        )


@dataclass
class EditCommand(ListingCommand):
    """二次编辑异步命令（PRD §3.12.13/ISSUE-0040）：单张 edit → 落图 → 终态「完成」。

    modifiers=路由已叠新的 effective（R3：落库与组装同值，每单自包含）；
    upload_keys=链根产品锚（role=product），源图经 source_image_key 列回显。
    """

    source_image: ReferenceImage
    anchor_images: tuple[ReferenceImage, ...]  # 链根原始产品图（与 anchor_keys 同序）
    anchor_keys: tuple[str, ...]
    parent_job_id: str
    source_image_key: str
    edit_mode: str  # delta | full

    async def _generate(self) -> ListingResult:
        return await self.service.edit(
            prompt=self.prompt,
            modifiers=self.modifiers,
            source_image=self.source_image,
            anchor_images=self.anchor_images,
            ratio=self.ratio,
            user_id=self.user_id,
            edit_mode=self.edit_mode,
        )

    def _start(self, job_id: str, size: str) -> ListingJobStart:
        return ListingJobStart(
            job_id=job_id,
            user_id=self.user_id,
            prompt=self.prompt,
            modifiers=self.modifiers,
            ratio=self.ratio,
            size=size,
            n=1,
            upload_keys=self.anchor_keys,
            input_roles=("product",) * len(self.anchor_keys),
            parent_job_id=self.parent_job_id,
            source_image_key=self.source_image_key,
            edit_mode=self.edit_mode,
        )


@dataclass
class CloneCommand(ListingCommand):
    """爆款复刻异步命令（PRD §3.13）：单张 clone → 落图 → 终态「完成」（含档位+双角色）。"""

    product_image: ReferenceImage
    reference_images: tuple[ReferenceImage, ...]
    upload_keys: tuple[str, ...]  # 保序：产品图在前、参考图在后（与喂图序一致）
    category: str | None
    clone_mode: str

    def _roles(self) -> tuple[str, ...]:
        return ("product",) + ("reference",) * len(self.reference_images)

    async def _generate(self) -> ListingResult:
        return await self.service.clone(
            prompt=self.prompt,
            modifiers=self.modifiers,
            product_image=self.product_image,
            reference_images=self.reference_images,
            ratio=self.ratio,
            user_id=self.user_id,
            category=self.category,
            clone_mode=self.clone_mode,
        )

    def _start(self, job_id: str, size: str) -> ListingJobStart:
        return ListingJobStart(
            job_id=job_id,
            user_id=self.user_id,
            prompt=self.prompt,
            modifiers=self.modifiers,
            ratio=self.ratio,
            size=size,
            n=1,
            upload_keys=self.upload_keys,
            input_roles=self._roles(),
            clone_mode=self.clone_mode,
            category=self.category,
        )
