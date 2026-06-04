from dataclasses import dataclass

from design_hub.application.pipeline import GenerationPipeline
from design_hub.domain.enums import TaskEventType
from design_hub.domain.models import Brief, TaskEvent
from design_hub.ports.events import EventPublisher
from design_hub.ports.job_repository import JobRepository
from design_hub.ports.task_queue import GenerationCommand


@dataclass
class PosterGenerationCommand(GenerationCommand):
    """海报流异步命令：跑 pipeline → 落库 → 沿途发进度事件（原 GenerationTaskRunner 逻辑）。

    brief/user_id 在构造时绑定，满足 GenerationCommand.run(job_id) 统一签名。
    """

    pipeline: GenerationPipeline
    jobs: JobRepository
    events: EventPublisher
    brief: Brief
    user_id: str

    async def run(self, job_id: str) -> None:
        await self.events.publish(TaskEvent(job_id, TaskEventType.TASK_STARTED, {}))
        try:
            result = await self.pipeline.run(self.brief, self.user_id)
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
            await self.jobs.save_completed(
                job_id=job_id, user_id=self.user_id, brief=self.brief, result=result
            )
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
