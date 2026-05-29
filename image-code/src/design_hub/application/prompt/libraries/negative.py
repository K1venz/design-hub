from design_hub.domain.enums import TemplateFamily

_COMMON = ["不要廉价电商风", "不要过度设计", "不要杂乱", "不要 AI 廉价感"]
_FESTIVE = ["不要俗气红", "不要复古酒吧风"]


class NegativeLibrary:
    """词库 B：通用负面 + 族7节庆负面。品类负面已迁入 CategoryProfile。"""

    def common(self) -> list[str]:
        return list(_COMMON)

    def for_family(self, family: TemplateFamily) -> list[str]:
        return list(_FESTIVE) if family is TemplateFamily.F7 else []
