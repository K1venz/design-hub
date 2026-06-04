from dataclasses import dataclass

from design_hub.application.listing.listing_service import ListingGenerationService
from design_hub.domain.enums import TaskEventType
from design_hub.domain.models import TaskEvent
from design_hub.ports.events import EventPublisher
from design_hub.ports.listing_history import ListingHistory
from design_hub.ports.task_queue import GenerationCommand


@dataclass
class ListingGenerationCommand(GenerationCommand):
    """listing 异步命令：service 出图 → 沿途发事件 → 历史口子（MVP NoOp）。"""

    service: ListingGenerationService
    events: EventPublisher
    history: ListingHistory
    user_id: str
    prompt: str
    modifiers: dict[str, str]
    images: tuple[bytes, ...]
    ratio: str
    n: int

    async def run(self, job_id: str) -> None:
        await self.events.publish(TaskEvent(job_id, TaskEventType.TASK_STARTED, {}))
        try:
            result = await self.service.generate(
                prompt=self.prompt,
                modifiers=self.modifiers,
                images=self.images,
                ratio=self.ratio,
                n=self.n,
                user_id=self.user_id,
            )
            await self.events.publish(
                TaskEvent(
                    job_id, TaskEventType.MODEL_CALLED, {"model": result.used_model.value}
                )
            )
            for image in result.images:
                await self.events.publish(
                    TaskEvent(
                        job_id,
                        TaskEventType.IMAGE_GENERATED,
                        {"url": image.url, "seed": image.seed},
                    )
                )
            await self.history.record(user_id=self.user_id, result=result)
            await self.events.publish(
                TaskEvent(
                    job_id,
                    TaskEventType.TASK_COMPLETED,
                    {"total_cost": str(result.total_cost)},
                )
            )
        except Exception as exc:
            await self.events.publish(
                TaskEvent(job_id, TaskEventType.TASK_FAILED, {"error": str(exc)})
            )
            raise
