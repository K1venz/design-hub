class ProviderError(Exception):
    """Model provider failure (network/IO domain — fallback is allowed here)."""


class ProviderTimeout(ProviderError):
    """Provider exceeded its latency budget."""
