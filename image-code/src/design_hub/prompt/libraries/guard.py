from ...domain.enums import Category

_GUARD: dict[Category, str] = {
    Category.DIGITAL_3C: "严格保持产品外观结构比例不变；屏幕/按键位置不变；接口结构清晰",
    Category.APPAREL: "手指不能遮挡核心结构；材质纹理清晰；五金件高光突出",
    Category.BEAUTY: "瓶身比例不变；Logo/标签文字清晰；瓶盖结构完整",
    Category.FOOD: "保留产品原色；避免过度调色；包装文字清晰",
    Category.WITH_PERSON: "原创模特，非明星脸，非真人复刻",
    Category.MIRROR: "反射干净，无杂乱人脸/背景；透明折射真实",
}


class GuardLibrary:
    """词库 C：歧义防御（按品类，防变形/遮挡/肖像权）。"""

    def get(self, category: Category) -> str:
        if category not in _GUARD:
            raise KeyError(f"No guard words for category {category}")
        return _GUARD[category]
