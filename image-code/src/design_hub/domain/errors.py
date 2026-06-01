class DomainError(Exception):
    """Base for non-IO domain errors. Propagated, never swallowed (fail-fast)."""


class NotFoundError(DomainError):
    """A referenced entity (project/brief/asset/...) does not exist. Maps to HTTP 404."""


class BudgetExceeded(DomainError):
    """A cost-guard red line was hit (PRD §3.9)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
