from dataclasses import dataclass
from decimal import Decimal

from design_hub.application.listing.listing_service import ListingGenerationService
from design_hub.application.listing.sizing import ratio_to_size
from design_hub.domain.enums import TaskEventType
from design_hub.domain.media import image_key_from_url
from design_hub.domain.models import ListingJobImage, ListingJobOutcome, TaskEvent
from design_hub.ports.events import EventPublisher
from design_hub.ports.listing_history import ListingHistory
from design_hub.ports.task_queue import GenerationCommand


@dataclass
class ListingGenerationCommand(GenerationCommand):
    """listing 异步命令：service 出图 → 沿途发事件 → 持久化任务/图/输入（成功与失败都落库）。"""

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
        await self.events.publish(TaskEvent(job_id, TaskEventType.TASK_STARTED, {}))
        size = "{}x{}".format(*ratio_to_size(self.ratio))
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
            await self.events.publish(
                TaskEvent(job_id, TaskEventType.TASK_FAILED, {"error": str(exc)})
            )
            await self.history.record(
                self._outcome(job_id, size, "失败", Decimal("0"), str(exc), ())
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
        for image_type, error in result.failures:  # 套图单张失败（D2：SSE 即时可见、不留痕）
            await self.events.publish(
                TaskEvent(
                    job_id,
                    TaskEventType.IMAGE_FAILED,
                    {"image_type": image_type, "error": error},
                )
            )
        images = tuple(
            ListingJobImage(
                image_key=image_key_from_url(im.url),
                seed=im.seed,
                cost=im.cost,
                status="成功",
                image_type=im.image_type,
            )
            for im in result.images
        )
        status = "完成" if len(images) >= self._requested() else "部分完成"
        await self.history.record(
            self._outcome(job_id, size, status, result.total_cost, None, images)
        )
        await self.events.publish(
            TaskEvent(
                job_id, TaskEventType.TASK_COMPLETED, {"total_cost": str(result.total_cost)}
            )
        )

    def _requested(self) -> int:
        """请求总张数：单图流=n、套图=Σplan（历史 n 列与状态判定共用）。"""
        return self.n if self.n is not None else sum((self.plan or {}).values())

    def _outcome(
        self,
        job_id: str,
        size: str,
        status: str,
        total_cost: Decimal,
        error: str | None,
        images: tuple[ListingJobImage, ...],
    ) -> ListingJobOutcome:
        return ListingJobOutcome(
            job_id=job_id,
            user_id=self.user_id,
            prompt=self.prompt,
            modifiers=self.modifiers,
            ratio=self.ratio,
            size=size,
            n=self._requested(),
            status=status,
            total_cost=total_cost,
            error=error,
            images=images,
            upload_keys=self.upload_keys,
        )


@dataclass
class CloneCommand(GenerationCommand):
    """爆款复刻异步命令（PRD §3.13）：service.clone 出 1 张 → 事件 → 持久化（含档位+双角色）。"""

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

    def _outcome(
        self,
        job_id: str,
        size: str,
        status: str,
        total_cost: Decimal,
        error: str | None,
        images: tuple[ListingJobImage, ...],
    ) -> ListingJobOutcome:
        return ListingJobOutcome(
            job_id=job_id,
            user_id=self.user_id,
            prompt=self.prompt,
            modifiers=self.modifiers,
            ratio=self.ratio,
            size=size,
            n=1,
            status=status,
            total_cost=total_cost,
            error=error,
            images=images,
            upload_keys=self.upload_keys,
            clone_mode=self.clone_mode,
            input_roles=self._roles(),
        )

    async def run(self, job_id: str) -> None:
        await self.events.publish(TaskEvent(job_id, TaskEventType.TASK_STARTED, {}))
        size = "{}x{}".format(*ratio_to_size(self.ratio))
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
            await self.events.publish(
                TaskEvent(job_id, TaskEventType.TASK_FAILED, {"error": str(exc)})
            )
            await self.history.record(
                self._outcome(job_id, size, "失败", Decimal("0"), str(exc), ())
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
        await self.history.record(
            self._outcome(job_id, size, "完成", result.total_cost, None, images)
        )
        await self.events.publish(
            TaskEvent(
                job_id, TaskEventType.TASK_COMPLETED, {"total_cost": str(result.total_cost)}
            )
        )
