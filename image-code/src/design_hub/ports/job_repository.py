from abc import ABC, abstractmethod

from design_hub.domain.models import Brief, GenerationResult, JobRecord


class JobRepository(ABC):
    """出图任务持久化端口（DIP）。"""

    @abstractmethod
    async def save_completed(
        self,
        *,
        user_id: str,
        brief: Brief,
        result: GenerationResult,
        project_id: int | None = None,
    ) -> str:
        """落库一条已完成任务及其候选图，返回 job_id。"""

    @abstractmethod
    async def get(self, job_id: str) -> JobRecord | None:
        ...
