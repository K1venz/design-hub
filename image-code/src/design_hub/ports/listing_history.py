from abc import ABC, abstractmethod

from design_hub.domain.models import ListingResult


class ListingHistory(ABC):
    """listing 出图历史持久化端口（架构口子）。MVP 绑 NoOp 不存；将来换 DB 实现，业务零改动。"""

    @abstractmethod
    async def record(self, *, user_id: str, result: ListingResult) -> None:
        ...
