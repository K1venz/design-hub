from decimal import Decimal

from design_hub.domain.models import BudgetSnapshot
from design_hub.ports.ledger import LedgerRepository


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
