from design_hub.application.prompt.profiles.category_profile import CategoryProfile
from design_hub.domain.enums import Category

FOOD = CategoryProfile(
    category=Category.FOOD,
    lens="50mm，f/2.8 近景，自然食欲色彩",
    composition="45°俯拍或平视，主体置黄金分割点，留白透气",
    position="画面视觉重心",
    angle="45°俯",
    light_form="侧逆暖光勾轮廓，柔和补光，营造食欲高光",
    props="新鲜食材点缀、餐布或木台、相关原料散落",
    guard="保留食品原色与质地；包装文字清晰；不夸大不失真",
    negatives=("不要塑料感", "不要假食物感", "不要过度调色"),
    fidelity="保持参考图食品/包装的形态、配色、文字与质地完全不变，仅重绘场景与光氛围",
)
