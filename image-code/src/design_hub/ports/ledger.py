from abc import ABC, abstractmethod
from decimal import Decimal

from design_hub.domain.models import BudgetSnapshot


class LedgerRepository(ABC):
    """成本流水仓储端口（DIP）；PG 实现按 LSP 替换内存实现。"""

    @abstractmethod
    async def snapshot(self, user_id: str) -> BudgetSnapshot:
        ...

    @abstractmethod
    async def reserve(
        self, user_id: str, amount: Decimal, *, operation_id: str
    ) -> None:
        ...

    @abstractmethod
    async def rollback(
        self, user_id: str, amount: Decimal, *, operation_id: str
    ) -> None:
        ...
