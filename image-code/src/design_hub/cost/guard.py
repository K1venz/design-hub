from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal
from functools import wraps

from .budget import BudgetPolicy
from .ledger import LedgerRepository


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
