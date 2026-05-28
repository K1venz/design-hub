import asyncio
from decimal import Decimal

from ..domain.dto import GeneratedImage
from ..domain.enums import ModelName
from .base import AbstractModelProvider
from .errors import ProviderTimeout


class MockModelProvider(AbstractModelProvider):
    """LSP-substitutable provider for CI: zero real API cost, controllable failure."""

    def __init__(
        self,
        *,
        name: ModelName = ModelName.SEEDREAM_5,
        unit_cost: Decimal = Decimal("0.20"),
        latency_ms: int = 5,
        fail: bool = False,
    ) -> None:
        self.name = name
        self.unit_cost = unit_cost
        self._latency_ms = latency_ms
        self._fail = fail

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
        await asyncio.sleep(self._latency_ms / 1000)
        if self._fail:
            raise ProviderTimeout(f"{self.name} mock failure")
        base = seed if seed is not None else 0
        return [
            GeneratedImage(
                url=f"mock://{self.name}/{base + i}.png",
                seed=base + i,
                latency_ms=self._latency_ms,
                cost=self.unit_cost,
            )
            for i in range(n)
        ]
