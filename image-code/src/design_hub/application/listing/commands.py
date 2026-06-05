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
    n: int

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
                user_id=self.user_id,
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
                    {"url": image.url, "seed": image.seed},
                )
            )
        images = tuple(
            ListingJobImage(
                image_key=image_key_from_url(im.url), seed=im.seed, cost=im.cost, status="成功"
            )
            for im in result.images
        )
        status = "完成" if len(images) >= self.n else "部分完成"
        await self.history.record(
            self._outcome(job_id, size, status, result.total_cost, None, images)
        )
        await self.events.publish(
            TaskEvent(
                job_id, TaskEventType.TASK_COMPLETED, {"total_cost": str(result.total_cost)}
            )
        )

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
            n=self.n,
            status=status,
            total_cost=total_cost,
            error=error,
            images=images,
            upload_keys=self.upload_keys,
        )
