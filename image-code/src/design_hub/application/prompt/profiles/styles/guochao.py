from design_hub.application.prompt.profiles.style_preset import StylePreset
from design_hub.domain.enums import Style

GUOCHAO = StylePreset(
    style=Style.GUOCHAO,
    color_card="中国红 #E60012 + 鎏金 #d4af37 + 墨黑 #1c1c1c",
    tint_a="暖米白",
    tint_b="浅金",
    light_color="暖金色调，红金辉映",
    mood="国潮喜庆、东方韵味",
    modifiers=("祥云回纹点缀", "鎏金质感", "新中式审美"),
)
