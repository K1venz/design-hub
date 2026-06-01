from abc import ABC, abstractmethod

from design_hub.domain.models import Brief, GenerationResult, JobRecord


class JobRepository(ABC):
    """出图任务持久化端口（DIP）。"""

    @abstractmethod
    async def save_completed(
        self,
        *,
        job_id: str,
        user_id: str,
        brief: Brief,
        result: GenerationResult,
        project_id: int | None = None,
        round_no: int = 1,
    ) -> str:
        """落库一条已完成任务及其候选图，返回 job_id（由调用方提供，与事件流一致）。

        round_no：项目下出图传项目当前轮次；脱离项目的独立出图为第 1 轮（默认）。
        """

    @abstractmethod
    async def get(self, job_id: str) -> JobRecord | None:
        ...
