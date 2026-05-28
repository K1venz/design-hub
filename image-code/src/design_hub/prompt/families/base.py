from abc import ABC, abstractmethod
from typing import ClassVar

from ...domain.enums import TemplateFamily


class TemplateFamilySkeleton(ABC):
    """模板族骨架基类（OCP/LSP：新增族 = 新增子类，统一 render 契约）。"""

    family: ClassVar[TemplateFamily]

    @abstractmethod
    def required_slots(self) -> set[str]:
        ...

    @abstractmethod
    def render(self, slots: dict[str, str]) -> str:
        ...

    def _check(self, slots: dict[str, str]) -> None:
        missing = self.required_slots() - slots.keys()
        if missing:
            raise KeyError(f"{self.family} missing slots: {sorted(missing)}")
