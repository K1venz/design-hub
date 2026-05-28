from design_hub.application.prompt.families.base import TemplateFamilySkeleton
from design_hub.application.prompt.families.family3 import Family3Minimal
from design_hub.application.prompt.families.family4 import Family4Premium
from design_hub.application.prompt.families.family5 import Family5Ambiance
from design_hub.application.prompt.families.family7 import Family7Festive
from design_hub.domain.enums import TemplateFamily


class FamilyRegistry:
    """V1 内置 4 族（3/4/5/7）；未实现族明确报错。"""

    def __init__(self) -> None:
        self._families: dict[TemplateFamily, TemplateFamilySkeleton] = {}
        for skeleton in (
            Family3Minimal(),
            Family4Premium(),
            Family5Ambiance(),
            Family7Festive(),
        ):
            self._families[skeleton.family] = skeleton

    def get(self, family: TemplateFamily) -> TemplateFamilySkeleton:
        if family not in self._families:
            raise KeyError(f"Template family {family} not implemented in V1")
        return self._families[family]
