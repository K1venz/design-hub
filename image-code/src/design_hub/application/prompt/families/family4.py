from typing import ClassVar

from design_hub.application.prompt.families.base import TemplateFamilySkeleton
from design_hub.domain.enums import TemplateFamily


class Family4Premium(TemplateFamilySkeleton):
    """族 4：高端商业摄影（单品精修/首图）。"""

    family: ClassVar[TemplateFamily] = TemplateFamily.F4

    def required_slots(self) -> set[str]:
        return {"镜头", "构图", "光影", "产品描述", "色卡", "氛围词", "用途", "比例"}

    def render(self, slots: dict[str, str]) -> str:
        self._check(slots)
        return (
            "超写实商业摄影质感。"
            f"{slots['镜头']}。{slots['构图']}。{slots['光影']}。"
            f"主体为{slots['产品描述']}。画面无人物。"
            f"主色调{slots['色卡']}。{slots['氛围词']}。"
            f"{slots['用途']}。{slots['比例']}"
        )
