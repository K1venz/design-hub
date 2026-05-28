from dataclasses import dataclass

from design_hub.application.pipeline import GenerationPipeline
from design_hub.domain.enums import TaskEventType
from design_hub.domain.models import Brief, TaskEvent
from design_hub.ports.events import EventPublisher
from design_hub.ports.job_repository import JobRepository


@dataclass
class GenerationTaskRunner:
    """异步出图任务编排（SRP）：跑 pipeline → 落库 → 沿途发进度事件。

    依赖 pipeline（M1，零改动）+ JobRepository/EventPublisher 端口（DIP）。
    """

    pipeline: GenerationPipeline
    jobs: JobRepository
    events: EventPublisher

    async def run(self, *, job_id: str, brief: Brief, user_id: str) -> str:
        await self.events.publish(TaskEvent(job_id, TaskEventType.TASK_STARTED, {}))
        try:
            result = await self.pipeline.run(brief, user_id)
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
            await self.jobs.save_completed(
                job_id=job_id, user_id=user_id, brief=brief, result=result
            )
            await self.events.publish(
                TaskEvent(
                    job_id,
                    TaskEventType.TASK_COMPLETED,
                    {"total_cost": str(result.total_cost)},
                )
            )
            return job_id
        except Exception as exc:
            await self.events.publish(
                TaskEvent(job_id, TaskEventType.TASK_FAILED, {"error": str(exc)})
            )
            raise
