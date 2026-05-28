from design_hub.domain.models import GeneratedImage
from design_hub.ports.model_provider import AbstractModelProvider, ProviderError


class FailoverModelProvider(AbstractModelProvider):
    """主备双中转 failover：同一模型、多个中转站按序尝试（DIP，不被单一供应商绑死）。

    与 pipeline 的"同档位换模型"正交：这里是同模型换网关。
    """

    def __init__(self, *, providers: list[AbstractModelProvider]) -> None:
        if not providers:
            raise ValueError("failover needs at least one provider")
        self._providers = providers
        self.name = providers[0].name
        self.unit_cost = providers[0].unit_cost

    async def generate(
        self,
        *,
        prompt: str,
        negative_prompt: str,
        reference_images: list[bytes],
        size: tuple[int, int],
        n: int,
        seed: int | None = None,
    ) -> list[GeneratedImage]:
        last_error: ProviderError | None = None
        for provider in self._providers:
            try:
                return await provider.generate(
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    reference_images=reference_images,
                    size=size,
                    n=n,
                    seed=seed,
                )
            except ProviderError as error:  # 网络/IO 域：切下一个中转站
                last_error = error
        raise last_error if last_error else ProviderError("failover: no provider available")
