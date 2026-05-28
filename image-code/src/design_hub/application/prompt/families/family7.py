from typing import ClassVar

from design_hub.application.prompt.families.base import TemplateFamilySkeleton
from design_hub.domain.enums import TemplateFamily


class Family7Festive(TemplateFamilySkeleton):
    """族 7：中式节庆促销（年货节/国潮/IP 大促）。"""

    family: ClassVar[TemplateFamily] = TemplateFamily.F7

    def required_slots(self) -> set[str]:
        return {
            "品牌",
            "主题场景名",
            "产品描述",
            "装饰元素",
            "主标题",
            "促销标语",
            "搜索词",
            "比例",
        }

    def render(self, slots: dict[str, str]) -> str:
        self._check(slots)
        return (
            "3D 电影感，C4D 风格，超大广角，超大透视，仰视角度，夸张视觉表现。"
            f"这是{slots['品牌']} \"{slots['主题场景名']}\" 主题场景，国风年味氛围。"
            f"主视觉元素：{slots['产品描述']}，鎏金材质。"
            f"场景细节：周围{slots['装饰元素']}，背景中式牌楼。"
            f"文字信息：顶部大标题 \"{slots['主标题']}\"，标语 \"{slots['促销标语']}\"，"
            f"底部搜索入口 \"{slots['搜索词']}\"。"
            f"光影：暖调金色光线。整体喜庆红火。{slots['比例']}"
        )
