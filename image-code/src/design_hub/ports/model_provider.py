from abc import ABC, abstractmethod
from decimal import Decimal

from design_hub.domain.enums import ModelName
from design_hub.domain.models import GeneratedImage


class ProviderError(Exception):
    """Model provider failure (network/IO domain — fallback is allowed here)."""


class ProviderTimeout(ProviderError):
    """Provider exceeded its latency budget."""


class AbstractModelProvider(ABC):
    """模型适配端口（ISP：唯一抽象方法 generate）。"""

    name: ModelName
    unit_cost: Decimal  # CNY per image

    @abstractmethod
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
        ...
