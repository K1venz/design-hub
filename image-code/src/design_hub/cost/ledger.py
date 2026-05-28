from abc import ABC, abstractmethod
from decimal import Decimal

from .budget import BudgetSnapshot


class LedgerRepository(ABC):
    """成本流水仓储接口（DIP）；M2 的 PG 实现按 LSP 直接替换内存实现。"""

    @abstractmethod
    async def snapshot(self, user_id: str) -> BudgetSnapshot:
        ...

    @abstractmethod
    async def reserve(self, user_id: str, amount: Decimal) -> None:
        ...

    @abstractmethod
    async def rollback(self, user_id: str, amount: Decimal) -> None:
        ...


class InMemoryLedgerRepository(LedgerRepository):
    def __init__(
        self,
        *,
        user_quota: Decimal = Decimal("200"),
        company_budget: Decimal = Decimal("800"),
    ) -> None:
        self._user_quota = user_quota
        self._company_budget = company_budget
        self._user_used: dict[str, Decimal] = {}
        self._company_used = Decimal("0")

    async def snapshot(self, user_id: str) -> BudgetSnapshot:
        return BudgetSnapshot(
            user_month_used=self._user_used.get(user_id, Decimal("0")),
            user_monthly_quota=self._user_quota,
            company_month_used=self._company_used,
            company_monthly_budget=self._company_budget,
        )

    async def reserve(self, user_id: str, amount: Decimal) -> None:
        self._user_used[user_id] = self._user_used.get(user_id, Decimal("0")) + amount
        self._company_used += amount

    async def rollback(self, user_id: str, amount: Decimal) -> None:
        self._user_used[user_id] = self._user_used.get(user_id, Decimal("0")) - amount
        self._company_used -= amount
