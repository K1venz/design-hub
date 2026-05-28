from arq.connections import ArqRedis

from design_hub.domain.models import Brief
from design_hub.infrastructure.queue.payload import brief_to_payload
from design_hub.ports.task_queue import TaskQueue


class ArqTaskQueue(TaskQueue):
    """TaskQueue 的 arq 实现：把出图任务投递到 Redis 队列。"""

    def __init__(self, pool: ArqRedis) -> None:
        self._pool = pool

    async def enqueue(self, *, job_id: str, brief: Brief, user_id: str) -> None:
        await self._pool.enqueue_job(
            "run_generation",
            {"job_id": job_id, "user_id": user_id, "brief": brief_to_payload(brief)},
        )
