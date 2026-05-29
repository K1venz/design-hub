from design_hub.application.prompt.profiles.style_preset import StylePreset
from design_hub.domain.enums import Style

FRESH = StylePreset(
    style=Style.FRESH,
    color_card="薄荷绿 #a8d8c0 + 浅木色 #d9c9b0 + 白 #ffffff",
    tint_a="薄荷白",
    tint_b="浅木",
    light_color="明亮自然光，清透色温",
    mood="清新自然、轻盈通透",
    modifiers=("自然光感", "清透通透", "小清新"),
)
