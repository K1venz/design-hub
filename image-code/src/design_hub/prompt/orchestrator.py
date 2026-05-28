from ..domain.dto import Brief, PromptPair
from ..domain.enums import ModelName
from .brand import BrandNameGenerator
from .families.registry import FamilyRegistry
from .libraries.color import ColorLibrary
from .libraries.guard import GuardLibrary
from .libraries.negative import NegativeLibrary
from .libraries.quality import QualityLibrary
from .rules import format_ratio, typography_block
from .vision import VisionAssist


class PromptOrchestrator:
    """编排器（DIP）：组合注入族注册表/词库/视觉/品牌生成器，按 playbook §五流程产出。"""

    def __init__(
        self,
        *,
        families: FamilyRegistry,
        colors: ColorLibrary,
        negatives: NegativeLibrary,
        guards: GuardLibrary,
        qualities: QualityLibrary,
        vision: VisionAssist,
        brands: BrandNameGenerator,
    ) -> None:
        self._families = families
        self._colors = colors
        self._negatives = negatives
        self._guards = guards
        self._qualities = qualities
        self._vision = vision
        self._brands = brands

    async def build(self, brief: Brief, target_model: ModelName) -> PromptPair:
        product_desc = brief.product_desc
        if product_desc is None:
            info = await self._vision.analyze(list(brief.reference_images))
            product_desc = (
                f"{info.material}{info.product_type}，主色{info.main_color_hex}，{info.shape_ratio}"
            )

        color_card = self._colors.get(brief.style)
        slots = self._build_slots(brief, product_desc, color_card, target_model)
        positive = self._families.get(brief.family).render(slots)

        # 法则4 防御词 + 法则6 文字独立段 + 法则10 质量词与比例收尾
        positive += "。" + self._guards.get(brief.category)
        positive += typography_block(brief.copy_text)
        positive += "。" + self._qualities.get(target_model)
        positive += " " + format_ratio(brief.size, target_model)

        negative = "、".join(self._negatives.build(brief.category, brief.family))
        return PromptPair(positive=positive, negative=negative)

    def _build_slots(
        self,
        brief: Brief,
        product_desc: str,
        color_card: str,
        target_model: ModelName,
    ) -> dict[str, str]:
        ratio = format_ratio(brief.size, target_model)
        brand = brief.brand_name or self._brands.candidates(brief.category, 1)[0]
        title = brief.copy_text or f"{brand} 臻选"
        return {
            "风格": brief.style.value,
            "品类": brief.category.value,
            "产品描述": product_desc,
            "色卡": color_card,
            "比例": ratio,
            "品牌": brand,
            "位置": "正中",
            "角度": "15°",
            "浅色A": "奶油白",
            "浅色B": "浅咖",
            "装饰元素": "柔光与几何点缀",
            "标题文案": title,
            "产品名": product_desc,
            "主标题": title,
            "促销标语": brief.copy_text or "限时优惠",
            "主题场景名": "新春",
            "搜索词": brand,
            "镜头": "50mm标准镜头，f/1.8大光圈，浅景深，近景特写",
            "构图": "居中留白，重心沉稳",
            "光影": "侧上方柔和暖光，明暗对比强烈",
            "氛围词": "高级沉浸氛围",
            "用途": f"电商{brief.category.value}广告主图",
        }
