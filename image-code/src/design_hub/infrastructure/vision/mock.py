from design_hub.domain.models import ProductVisualInfo
from design_hub.ports.vision import VisionAssist


class MockVisionAssist(VisionAssist):
    async def analyze(self, images: list[bytes]) -> ProductVisualInfo:
        return ProductVisualInfo(
            product_type="通用产品",
            main_color_hex="#cccccc",
            material="哑光塑料",
            shape_ratio="竖向圆柱",
            logo_position="正面居中",
        )
