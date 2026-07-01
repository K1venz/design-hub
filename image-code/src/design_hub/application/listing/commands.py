from dataclasses import dataclass
from decimal import Decimal

from design_hub.application.listing.listing_service import ListingGenerationService
from design_hub.application.listing.sizing import ratio_to_size
from design_hub.domain.enums import TaskEventType
from design_hub.domain.media import image_key_from_url
from design_hub.domain.models import ListingJobImage, ListingJobStart, TaskEvent
from design_hub.ports.events import EventPublisher
from design_hub.ports.listing_history import ListingHistory
from design_hub.ports.task_queue import GenerationCommand

# 失败张（套图部分完成）无产物：image_key 空串占位、seed 哨兵；读侧按 status 区分、不签 url。
_FAILED_IMAGE_KEY = ""
_FAILED_SEED = -1


def _failure_summary(failures: tuple[tuple[str, str], ...]) -> str:
    """套图部分失败摘要（图型：原因），落 listing_job.error（既有列，无 per-image 原因列）。"""
    return "；".join(f"{image_type}：{error}" for image_type, error in failures)


@dataclass
class ListingGenerationCommand(GenerationCommand):
    """listing 异步命令：入队建行(生成中) → service 出图 → 增量落图(成功+失败) → 终态改状态。

    两阶段落库（ISSUE-0047）：进行中单在 DB 即有行、可查、可续播；套图失败张也留痕。
    """

    service: ListingGenerationService
    events: EventPublisher
    history: ListingHistory
    user_id: str
    prompt: str
    modifiers: dict[str, str]
    images: tuple[bytes, ...]
    upload_keys: tuple[str, ...]
    ratio: str
    category: str
    n: int | None = None
    plan: dict[str, int] | None = None  # 套图配比（与 n 互斥，PRD §3.12.14）
    overlay_texts: tuple[str, ...] = ()

    async def run(self, job_id: str) -> None:
        size = "{}x{}".format(*ratio_to_size(self.ratio))
        await self.history.start(self._start(job_id, size))  # 入队建行：status='生成中'
        await self.events.publish(TaskEvent(job_id, TaskEventType.TASK_STARTED, {}))
        try:
            result = await self.service.generate(
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
        except Exception as exc:
            await self.history.finalize(
                job_id, status="失败", total_cost=Decimal("0"), error=str(exc)
            )
            await self.events.publish(
                TaskEvent(job_id, TaskEventType.TASK_FAILED, {"error": str(exc)})
            )
            raise
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
        for image_type, error in result.failures:  # 套图单张失败（SSE 即时可见）
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
        )


@dataclass
class EditCommand(GenerationCommand):
    """二次编辑异步命令（PRD §3.12.13/ISSUE-0040）：建行 → service.edit 出 1 张 → 落图 → 终态。

    modifiers=路由已叠新的 effective（R3：落库与组装同值，每单自包含）；
    upload_keys=链根产品锚（role=product），源图经 source_image_key 列回显。
    """

    service: ListingGenerationService
    events: EventPublisher
    history: ListingHistory
    user_id: str
    prompt: str
    modifiers: dict[str, str]
    source_image: bytes
    anchor_images: tuple[bytes, ...]  # 链根原始产品图（与 anchor_keys 同序）
    anchor_keys: tuple[str, ...]
    parent_job_id: str
    source_image_key: str
    ratio: str
    edit_mode: str  # delta | full

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

    async def run(self, job_id: str) -> None:
        size = "{}x{}".format(*ratio_to_size(self.ratio))
        await self.history.start(self._start(job_id, size))
        await self.events.publish(TaskEvent(job_id, TaskEventType.TASK_STARTED, {}))
        try:
            result = await self.service.edit(
                prompt=self.prompt,
                modifiers=self.modifiers,
                source_image=self.source_image,
                anchor_images=self.anchor_images,
                ratio=self.ratio,
                user_id=self.user_id,
                edit_mode=self.edit_mode,
            )
        except Exception as exc:
            await self.history.finalize(
                job_id, status="失败", total_cost=Decimal("0"), error=str(exc)
            )
            await self.events.publish(
                TaskEvent(job_id, TaskEventType.TASK_FAILED, {"error": str(exc)})
            )
            raise
        await self.events.publish(
            TaskEvent(job_id, TaskEventType.MODEL_CALLED, {"model": result.used_model.value})
        )
        for image in result.images:
            await self.events.publish(
                TaskEvent(
                    job_id,
                    TaskEventType.IMAGE_GENERATED,
                    {"url": image.url, "seed": image.seed, "image_type": None},
                )
            )
        images = tuple(
            ListingJobImage(
                image_key=image_key_from_url(im.url), seed=im.seed, cost=im.cost, status="成功"
            )
            for im in result.images
        )
        await self.history.add_images(job_id, images)
        await self.history.finalize(
            job_id, status="完成", total_cost=result.total_cost, error=None
        )
        await self.events.publish(
            TaskEvent(
                job_id, TaskEventType.TASK_COMPLETED, {"total_cost": str(result.total_cost)}
            )
        )


@dataclass
class CloneCommand(GenerationCommand):
    """爆款复刻异步命令（PRD §3.13）：建行 → clone 出 1 张 → 落图 → 终态（含档位+双角色）。"""

    service: ListingGenerationService
    events: EventPublisher
    history: ListingHistory
    user_id: str
    prompt: str
    modifiers: dict[str, str]
    product_image: bytes
    reference_images: tuple[bytes, ...]
    upload_keys: tuple[str, ...]  # 保序：产品图在前、参考图在后（与喂图序一致）
    ratio: str
    category: str
    clone_mode: str

    def _roles(self) -> tuple[str, ...]:
        return ("product",) + ("reference",) * len(self.reference_images)

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
        )

    async def run(self, job_id: str) -> None:
        size = "{}x{}".format(*ratio_to_size(self.ratio))
        await self.history.start(self._start(job_id, size))
        await self.events.publish(TaskEvent(job_id, TaskEventType.TASK_STARTED, {}))
        try:
            result = await self.service.clone(
                prompt=self.prompt,
                modifiers=self.modifiers,
                product_image=self.product_image,
                reference_images=self.reference_images,
                ratio=self.ratio,
                user_id=self.user_id,
                category=self.category,
                clone_mode=self.clone_mode,
            )
        except Exception as exc:
            await self.history.finalize(
                job_id, status="失败", total_cost=Decimal("0"), error=str(exc)
            )
            await self.events.publish(
                TaskEvent(job_id, TaskEventType.TASK_FAILED, {"error": str(exc)})
            )
            raise
        await self.events.publish(
            TaskEvent(job_id, TaskEventType.MODEL_CALLED, {"model": result.used_model.value})
        )
        for image in result.images:
            await self.events.publish(
                TaskEvent(
                    job_id,
                    TaskEventType.IMAGE_GENERATED,
                    {"url": image.url, "seed": image.seed, "image_type": None},
                )
            )
        images = tuple(
            ListingJobImage(
                image_key=image_key_from_url(im.url), seed=im.seed, cost=im.cost, status="成功"
            )
            for im in result.images
        )
        await self.history.add_images(job_id, images)
        await self.history.finalize(
            job_id, status="完成", total_cost=result.total_cost, error=None
        )
        await self.events.publish(
            TaskEvent(
                job_id, TaskEventType.TASK_COMPLETED, {"total_cost": str(result.total_cost)}
            )
        )
