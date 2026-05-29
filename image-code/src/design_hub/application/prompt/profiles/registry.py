from design_hub.application.prompt.profiles.categories.apparel import APPAREL
from design_hub.application.prompt.profiles.categories.beauty import BEAUTY
from design_hub.application.prompt.profiles.categories.digital import DIGITAL
from design_hub.application.prompt.profiles.categories.food import FOOD
from design_hub.application.prompt.profiles.category_profile import CategoryProfile
from design_hub.application.prompt.profiles.style_preset import StylePreset
from design_hub.application.prompt.profiles.styles.fresh import FRESH
from design_hub.application.prompt.profiles.styles.guochao import GUOCHAO
from design_hub.application.prompt.profiles.styles.luxury import LUXURY
from design_hub.application.prompt.profiles.styles.nordic import NORDIC
from design_hub.application.prompt.profiles.styles.sport import SPORT
from design_hub.application.prompt.profiles.styles.tech import TECH
from design_hub.domain.enums import Category, Style


class CategoryProfileRegistry:
    """V1 内置 4 品类画像；未注册品类 fail-fast。"""

    def __init__(self) -> None:
        self._profiles: dict[Category, CategoryProfile] = {}
        for profile in (DIGITAL, FOOD, BEAUTY, APPAREL):
            self._profiles[profile.category] = profile

    def get(self, category: Category) -> CategoryProfile:
        if category not in self._profiles:
            raise KeyError(f"No category profile for {category}")
        return self._profiles[category]


class StylePresetRegistry:
    """V1 内置 6 风格预设；未注册风格 fail-fast。"""

    def __init__(self) -> None:
        self._presets: dict[Style, StylePreset] = {}
        for preset in (GUOCHAO, NORDIC, LUXURY, TECH, FRESH, SPORT):
            self._presets[preset.style] = preset

    def get(self, style: Style) -> StylePreset:
        if style not in self._presets:
            raise KeyError(f"No style preset for {style}")
        return self._presets[style]
