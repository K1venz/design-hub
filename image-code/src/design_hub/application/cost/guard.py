from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal
from functools import wraps

from design_hub.application.cost.budget import BudgetPolicy
from design_hub.ports.ledger import LedgerRepository


@dataclass
class CostGuard:
    ledger: LedgerRepository
    policy: BudgetPolicy

    async def precheck_and_reserve(self, user_id: str, estimate: Decimal) -> None:
        snapshot = await self.ledger.snapshot(user_id)
        self.policy.check(estimate, snapshot)  # raises BudgetExceeded
        await self.ledger.reserve(user_id, estimate)

    async def rollback(self, user_id: str, estimate: Decimal) -> None:
        await self.ledger.rollback(user_id, estimate)

    async def reconcile(self, user_id: str, *, reserved: Decimal, actual: Decimal) -> None:
        """把按主模型预扣的额度回正到实际成本（PRD §3.9，append-only 补差额）。

        fallback 到更便宜/更贵的同档备选成功后，预扣(reserved)与实际(actual)会分叉；
        在此补一笔差额，使 ledger 净额 = 实际成本，与 generation_job/仪表盘一致。
        """
        delta = actual - reserved
        if delta > 0:
            await self.ledger.reserve(user_id, delta)
        elif delta < 0:
            await self.ledger.rollback(user_id, -delta)


@dataclass
class GuardContext:
    user_id: str
    estimate: Decimal
    guard: CostGuard


def cost_guard[T](
    func: Callable[[GuardContext], Awaitable[T]],
) -> Callable[[GuardContext], Awaitable[T]]:
    """PRD §3.9：入队前预扣额度，任务失败回滚。包裹任务入口函数。"""

    @wraps(func)
    async def wrapper(ctx: GuardContext) -> T:
        await ctx.guard.precheck_and_reserve(ctx.user_id, ctx.estimate)
        try:
            return await func(ctx)
        except Exception:
            await ctx.guard.rollback(ctx.user_id, ctx.estimate)
            raise

    return wrapper
