from ..domain.enums import ModelName
from .base import AbstractModelProvider


class ProviderRegistry:
    """DIP assembly root: pipeline resolves providers by name, not by import."""

    def __init__(self) -> None:
        self._providers: dict[ModelName, AbstractModelProvider] = {}

    def register(self, provider: AbstractModelProvider) -> None:
        self._providers[provider.name] = provider

    def get(self, name: ModelName) -> AbstractModelProvider:
        if name not in self._providers:
            raise KeyError(f"No provider registered for {name}")
        return self._providers[name]

    def __contains__(self, name: ModelName) -> bool:
        return name in self._providers
