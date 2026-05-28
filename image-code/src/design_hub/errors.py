class DomainError(Exception):
    """Base for non-IO domain errors. Propagated, never swallowed (fail-fast)."""
