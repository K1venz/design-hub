from design_hub.application.prompt.profiles.category_profile import CategoryProfile
from design_hub.domain.enums import Category

BEAUTY = CategoryProfile(
    category=Category.BEAUTY,
    lens="85mm，f/4，柔焦近景，瓶身高光干净",
    composition="居中或对称，留充足文案空间",
    position="正中偏上",
    angle="正面平视",
    light_form="柔光箱均匀布光，瓶身边缘高光，倒影干净",
    props="水波、丝绸或花瓣等柔质点缀，呼应成分",
    guard="瓶身比例不变；Logo/标签文字清晰；瓶盖结构完整",
    negatives=("不要标签文字模糊", "不要瓶型变形", "不要廉价塑料反光"),
    fidelity="保持参考图美妆瓶身的轮廓、标签文字、Logo、瓶盖结构完全不变，仅重绘背景与光影",
)
