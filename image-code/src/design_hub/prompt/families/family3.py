from typing import ClassVar

from ...domain.enums import TemplateFamily
from .base import TemplateFamilySkeleton


class Family3Minimal(TemplateFamilySkeleton):
    """族 3：极简电商主图（美妆/护肤/保健）。"""

    family: ClassVar[TemplateFamily] = TemplateFamily.F3

    def required_slots(self) -> set[str]:
        return {
            "风格",
            "品类",
            "产品描述",
            "位置",
            "角度",
            "浅色A",
            "浅色B",
            "装饰元素",
            "色卡",
            "标题文案",
            "比例",
        }

    def render(self, slots: dict[str, str]) -> str:
        self._check(slots)
        return (
            f"极简主义{slots['风格']}{slots['品类']}电商海报。"
            f"主体产品是{slots['产品描述']}。"
            f"产品位于画面{slots['位置']}，呈{slots['角度']}倾斜。"
            f"背景为{slots['浅色A']}至{slots['浅色B']}渐变。"
            f"产品周围{slots['装饰元素']}，营造柔和景深层次。"
            f"专业棚拍布光，排版干净，留有充足文案空间，8k，"
            f"高端{slots['品类']}广告摄影风格。{slots['比例']}\n"
            f"【文字排版】主色调：{slots['色卡']}；主标题：{slots['标题文案']}"
        )
