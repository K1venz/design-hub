from decimal import Decimal

from design_hub.domain.errors import BudgetExceeded
from design_hub.domain.models import BudgetSnapshot


class BudgetPolicy:
    """PRD §3.9 三条红线（顺序：公司总预算 → 用户配额 → 单次占比）。"""

    def check(self, estimate: Decimal, snapshot: BudgetSnapshot) -> None:
        company_remaining = snapshot.company_monthly_budget - snapshot.company_month_used
        if company_remaining <= 0:
            raise BudgetExceeded("公司本月预算已用尽，需管理者手动解锁")
        if snapshot.user_month_used >= snapshot.user_monthly_quota:
            raise BudgetExceeded("用户本月配额已用尽")
        if estimate > company_remaining * Decimal("0.5"):
            raise BudgetExceeded("单次任务超过公司剩余预算的 50%")
