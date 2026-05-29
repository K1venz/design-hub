from design_hub.application.prompt.brand import BrandNameGenerator
from design_hub.application.prompt.families.registry import FamilyRegistry
from design_hub.application.prompt.libraries.negative import NegativeLibrary
from design_hub.application.prompt.libraries.quality import QualityLibrary
from design_hub.application.prompt.profiles.category_profile import CategoryProfile
from design_hub.application.prompt.profiles.registry import (
    CategoryProfileRegistry,
    StylePresetRegistry,
)
from design_hub.application.prompt.profiles.style_preset import StylePreset
from design_hub.application.prompt.rules import format_ratio, typography_block
from design_hub.domain.enums import GenMode, ModelName
from design_hub.domain.models import Brief, PromptPair
from design_hub.ports.vision import VisionAssist


class PromptOrchestrator:
    """编排器（DIP）：组合注入族/品类画像/风格预设/词库/视觉/品牌。

    三维正交：模板族(骨架) × 品类画像(物性) × 风格预设(调性)。
    光影按"光型(品类)+光色(风格)"拼接，不覆盖。
    """

    def __init__(
        self,
        *,
        families: FamilyRegistry,
        categories: CategoryProfileRegistry,
        styles: StylePresetRegistry,
        negatives: NegativeLibrary,
        qualities: QualityLibrary,
        vision: VisionAssist,
        brands: BrandNameGenerator,
    ) -> None:
        self._families = families
        self._categories = categories
        self._styles = styles
        self._negatives = negatives
        self._qualities = qualities
        self._vision = vision
        self._brands = brands

    async def build(
        self,
        brief: Brief,
        target_model: ModelName,
        mode: GenMode = GenMode.TEXT2IMG,
    ) -> PromptPair:
        profile = self._categories.get(brief.category)
        preset = self._styles.get(brief.style)

        product_desc = brief.product_desc
        if product_desc is None:
            info = await self._vision.analyze(list(brief.reference_images))
            product_desc = (
                f"{info.material}{info.product_type}，主色{info.main_color_hex}，{info.shape_ratio}"
            )

        slots = self._build_slots(brief, profile, preset, product_desc, target_model)
        positive = self._families.get(brief.family).render(slots)

        # 法则4 防御词
        positive += "。" + profile.guard
        # 法则6 文字独立段
        positive += typography_block(brief.copy_text)
        # 图生图 EDIT：追加产品保真约束
        if mode is GenMode.EDIT:
            positive += "。" + profile.fidelity
        # 风格修饰（preset.modifiers，整图调性，仅一次）
        positive += "。风格修饰：" + "、".join(preset.modifiers)
        # 法则10 质量词（按模型，仅一次；比例已由骨架槽承担，不再追加）
        positive += "。" + self._qualities.get(target_model)

        negative_items = self._negatives.common()
        negative_items += list(profile.negatives)
        negative_items += self._negatives.for_family(brief.family)
        negative = "、".join(dict.fromkeys(negative_items))  # 去重保序
        return PromptPair(positive=positive, negative=negative)

    def _build_slots(
        self,
        brief: Brief,
        profile: CategoryProfile,
        preset: StylePreset,
        product_desc: str,
        target_model: ModelName,
    ) -> dict[str, str]:
        ratio = format_ratio(brief.size, target_model)
        brand = brief.brand_name or self._brands.candidates(brief.category, 1)[0]
        title = brief.copy_text or f"{brand} 臻选"
        return {
            "风格": brief.style.value,
            "品类": brief.category.value,
            "产品描述": product_desc,
            "色卡": preset.color_card,
            "比例": ratio,
            "品牌": brand,
            # 品类画像（物性）
            "位置": profile.position,
            "角度": profile.angle,
            "镜头": profile.lens,
            "构图": profile.composition,
            "装饰元素": profile.props,
            # 光影 = 光型(品类) + 光色(风格)，拼接不覆盖
            "光影": f"{profile.light_form}，{preset.light_color}",
            # 风格预设（调性）
            "浅色A": preset.tint_a,
            "浅色B": preset.tint_b,
            "氛围词": preset.mood,
            # 文案类
            "标题文案": title,
            "产品名": product_desc,
            "主标题": title,
            "促销标语": brief.copy_text or "限时优惠",
            "主题场景名": "新春",
            "搜索词": brand,
            "用途": f"电商{brief.category.value}广告主图",
        }
