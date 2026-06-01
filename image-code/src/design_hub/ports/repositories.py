from abc import ABC, abstractmethod
from collections.abc import Sequence

from design_hub.domain.enums import ProjectStatus
from design_hub.domain.models import CustomerRecord, ProjectRecord


class CustomerRepository(ABC):
    """客户档案仓储端口（DIP）。"""

    @abstractmethod
    async def create(
        self,
        *,
        name: str,
        contact: str | None = None,
        industry: str | None = None,
        brand_color: str | None = None,
        common_styles: Sequence[str] = (),
        common_taboos: Sequence[str] = (),
        common_sizes: Sequence[str] = (),
    ) -> CustomerRecord:
        ...

    @abstractmethod
    async def get(self, customer_id: int) -> CustomerRecord | None:
        ...

    @abstractmethod
    async def list(self) -> list[CustomerRecord]:
        ...


class ProjectRepository(ABC):
    """项目仓储端口（DIP）。"""

    @abstractmethod
    async def create(self, *, customer_id: int, name: str) -> ProjectRecord:
        ...

    @abstractmethod
    async def get(self, project_id: int) -> ProjectRecord | None:
        ...

    @abstractmethod
    async def list(self, *, customer_id: int | None = None) -> list[ProjectRecord]:
        ...

    @abstractmethod
    async def set_status(self, project_id: int, status: ProjectStatus) -> ProjectRecord:
        ...
