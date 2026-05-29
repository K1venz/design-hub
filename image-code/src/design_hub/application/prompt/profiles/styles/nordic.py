from design_hub.application.prompt.profiles.style_preset import StylePreset
from design_hub.domain.enums import Style

NORDIC = StylePreset(
    style=Style.NORDIC,
    color_card="鼠尾草绿 #b2c2a8 + 牛皮纸 #d4c4a0 + 奶油白 #f5f0e6",
    tint_a="奶油白",
    tint_b="浅燕麦",
    light_color="自然柔光，中性色温",
    mood="极简克制、留白通透",
    modifiers=("大量留白", "极简构成", "ins 北欧风"),
)
