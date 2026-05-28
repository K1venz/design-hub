from typing import ClassVar

from ...domain.enums import TemplateFamily
from .base import TemplateFamilySkeleton


class Family5Ambiance(TemplateFamilySkeleton):
    """族 5：氛围沉浸场景（食品/咖啡/生活方式）。"""

    family: ClassVar[TemplateFamily] = TemplateFamily.F5

    def required_slots(self) -> set[str]:
        return {"风格", "产品名", "色卡", "装饰元素", "标题文案", "比例"}

    def render(self, slots: dict[str, str]) -> str:
        self._check(slots)
        return (
            f"一张{slots['风格']}「{slots['产品名']}」产品宣传海报，"
            "电商广告与品牌视觉结合风格。"
            f"背景使用{slots['色卡']}，营造沉浸氛围。"
            f"主体立体摆放，{slots['装饰元素']}。"
            f"主标题：{slots['标题文案']}。"
            f"要求高级质感、非AI廉价感。{slots['比例']}"
        )
