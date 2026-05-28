from ...domain.enums import TemplateFamily
from .base import TemplateFamilySkeleton
from .family3 import Family3Minimal
from .family4 import Family4Premium
from .family5 import Family5Ambiance
from .family7 import Family7Festive


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
