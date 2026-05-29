from design_hub.application.prompt.profiles.style_preset import StylePreset
from design_hub.domain.enums import Style

TECH = StylePreset(
    style=Style.TECH,
    color_card="深空蓝 #0a1428 + 电光紫 #8b5cf6 + 冷银 #c0c8d0",
    tint_a="冷灰",
    tint_b="深蓝黑",
    light_color="冷调光，蓝紫氛围光",
    mood="未来科技、冷峻精密",
    modifiers=("光效线条", "金属冷光", "科技感"),
)
