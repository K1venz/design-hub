from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from design_hub.domain.models import BudgetSnapshot
from design_hub.infrastructure.db.models import CostLedgerEntry
from design_hub.ports.ledger import LedgerRepository


def _month_start() -> datetime:
    # 当月起点（朴素 UTC，与 MySQL/sqlite 的朴素 DATETIME 存储对齐）
    now = datetime.now(UTC).replace(tzinfo=None)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


class SqlAlchemyLedgerRepository(LedgerRepository):
    """LedgerRepository 的 SQLAlchemy 实现，按 LSP 替换内存版。

    cost_ledger 为 append-only 流水：预扣写 +amount，回滚写 -amount，
    当月用量 = 当月该用户/全公司 amount 之和。
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        user_quota: Decimal = Decimal("200"),
        company_budget: Decimal = Decimal("800"),
    ) -> None:
        self._session_factory = session_factory
        self._user_quota = user_quota
        self._company_budget = company_budget

    async def snapshot(self, user_id: str) -> BudgetSnapshot:
        start = _month_start()
        total = func.coalesce(func.sum(CostLedgerEntry.amount), 0)
        async with self._session_factory() as session:
            user_used = (
                await session.execute(
                    select(total).where(
                        CostLedgerEntry.user_id == user_id,
                        CostLedgerEntry.created_at >= start,
                    )
                )
            ).scalar_one()
            company_used = (
                await session.execute(
                    select(total).where(CostLedgerEntry.created_at >= start)
                )
            ).scalar_one()
        return BudgetSnapshot(
            user_month_used=Decimal(str(user_used)),
            user_monthly_quota=self._user_quota,
            company_month_used=Decimal(str(company_used)),
            company_monthly_budget=self._company_budget,
        )

    async def reserve(self, user_id: str, amount: Decimal) -> None:
        async with self._session_factory() as session:
            session.add(CostLedgerEntry(user_id=user_id, amount=amount))
            await session.commit()

    async def rollback(self, user_id: str, amount: Decimal) -> None:
        async with self._session_factory() as session:
            session.add(CostLedgerEntry(user_id=user_id, amount=-amount))
            await session.commit()
