from abc import ABC, abstractmethod

from design_hub.domain.models import Brief


class TaskQueue(ABC):
    """出图任务入队端口（DIP）；arq 适配器实现，测试可用假实现。"""

    @abstractmethod
    async def enqueue(self, *, job_id: str, brief: Brief, user_id: str) -> None:
        ...
