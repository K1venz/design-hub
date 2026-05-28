from abc import ABC, abstractmethod
from decimal import Decimal

from ..domain.dto import GeneratedImage
from ..domain.enums import ModelName


class AbstractModelProvider(ABC):
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
