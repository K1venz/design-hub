from design_hub.ports.model_provider import AbstractModelProvider


class ProviderRegistry:
    """DIP 组装根：按稳定模型 ID 注册/取用 Provider，pipeline 不依赖具体适配器。"""

    def __init__(self) -> None:
        self._providers: dict[str, AbstractModelProvider] = {}

    def register(self, provider: AbstractModelProvider) -> None:
        self._providers[provider.name] = provider

    def get(self, name: str) -> AbstractModelProvider:
        if name not in self._providers:
            raise KeyError(f"No provider registered for {name}")
        return self._providers[name]

    def __contains__(self, name: str) -> bool:
        return name in self._providers
