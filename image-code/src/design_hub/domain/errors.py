class DomainError(Exception):
    """Base for non-IO domain errors. Propagated, never swallowed (fail-fast)."""


class BudgetExceeded(DomainError):
    """A cost-guard red line was hit (PRD §3.9)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
