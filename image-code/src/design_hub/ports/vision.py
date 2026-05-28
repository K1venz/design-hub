from abc import ABC, abstractmethod

from design_hub.domain.models import ProductVisualInfo


class VisionAssist(ABC):
    """视觉理解辅助端口（ISP/DIP）；真实 qwen-vl-max 作为另一适配器注入。"""

    @abstractmethod
    async def analyze(self, images: list[bytes]) -> ProductVisualInfo:
        ...
