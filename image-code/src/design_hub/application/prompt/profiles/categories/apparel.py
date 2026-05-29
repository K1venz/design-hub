from design_hub.application.prompt.profiles.category_profile import CategoryProfile
from design_hub.domain.enums import Category

APPAREL = CategoryProfile(
    category=Category.APPAREL,
    lens="35mm，f/5.6，平铺或挂拍，纹理清晰",
    composition="居中平铺或立体悬挂，留白均衡",
    position="正中",
    angle="正面平视",
    light_form="大面积柔光，斜侧光强调面料纹理与褶皱立体",
    props="极简衣架或台面，少量配饰呼应",
    guard="手指/道具不遮挡核心结构；面料纹理清晰；五金件高光突出",
    negatives=("不要面料失真", "不要褶皱杂乱", "不要廉价化纤反光"),
    fidelity="保持参考图服饰的版型、面料纹理、颜色、印花与五金件完全不变，仅重绘背景与光影",
)
