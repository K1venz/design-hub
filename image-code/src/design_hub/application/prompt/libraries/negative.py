from design_hub.domain.enums import Category, TemplateFamily

_COMMON = ["不要廉价电商风", "不要过度设计", "不要杂乱", "不要 AI 廉价感"]
_BY_CATEGORY: dict[Category, list[str]] = {
    Category.WITH_PERSON: ["不要普通街拍", "不要全身穿搭展示", "不要电商白底图"],
    Category.FOOD: ["不要过度调色", "不要塑料感", "不要假食物感"],
    Category.MIRROR: ["不要镜面杂乱反射", "不要出现杂乱人脸"],
}
_FESTIVE = ["不要俗气红", "不要复古酒吧风"]


class NegativeLibrary:
    """词库 B：中文场景化负面句（通用 + 按品类 + 节庆叠加）。"""

    def build(self, category: Category, family: TemplateFamily) -> list[str]:
        items = list(_COMMON)
        items += _BY_CATEGORY.get(category, [])
        if family is TemplateFamily.F7:
            items += _FESTIVE
        return items
