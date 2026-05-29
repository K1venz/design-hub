from design_hub.application.prompt.profiles.category_profile import CategoryProfile
from design_hub.domain.enums import Category

DIGITAL = CategoryProfile(
    category=Category.DIGITAL_3C,
    lens="45°微距，f/8 深景深，控制金属反光",
    composition="居中正交构图，留白克制，重心沉稳",
    position="正中",
    angle="正面平视微俯",
    light_form="硬光勾勒金属边缘，柔光补面，反光可控",
    props="极简几何垫块，深色磨砂台面，无杂物",
    guard="严格保持产品外观结构比例不变；屏幕/按键/接口位置不变；金属与玻璃质感真实",
    negatives=("不要塑料廉价感", "不要错位接口", "不要多余按键"),
    fidelity="保持参考图数码产品机身线条、屏幕、按键接口布局、Logo 不变，仅重绘环境光影",
)
