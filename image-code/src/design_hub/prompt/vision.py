from abc import ABC, abstractmethod

from ..domain.dto import ProductVisualInfo


class VisionAssist(ABC):
    """视觉理解辅助接口（ISP/DIP）；真实 qwen-vl-max 作为另一实现注入。"""

    @abstractmethod
    async def analyze(self, images: list[bytes]) -> ProductVisualInfo:
        ...


class MockVisionAssist(VisionAssist):
    async def analyze(self, images: list[bytes]) -> ProductVisualInfo:
        return ProductVisualInfo(
            product_type="通用产品",
            main_color_hex="#cccccc",
            material="哑光塑料",
            shape_ratio="竖向圆柱",
            logo_position="正面居中",
        )
