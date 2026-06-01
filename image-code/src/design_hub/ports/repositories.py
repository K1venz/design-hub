# 注解延迟为字符串：类体期不求值，根除 `list` 等方法名遮蔽内置类型导致的注解崩溃
# （ISSUE-0004：AssetRepository.list 遮蔽 list，后续 get_many 的 list[...] 注解求值 TypeError）
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import Any

from design_hub.domain.enums import AssetKind, ProjectStatus
from design_hub.domain.models import (
    AssetRecord,
    BriefRecord,
    CustomerRecord,
    ProjectRecord,
)


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


class BriefRepository(ABC):
    """标准化需求单仓储端口（DIP）。一项目一需求单（upsert 语义）。"""

    @abstractmethod
    async def upsert(
        self,
        *,
        project_id: int,
        material_types: Sequence[str] = (),
        sizes: Sequence[str] = (),
        styles: Sequence[str] = (),
        resolution: str | None = None,
        bleed: str | None = None,
        copy_text: str | None = None,
        taboo: str | None = None,
        delivery: Mapping[str, Any] | None = None,
    ) -> BriefRecord:
        ...

    @abstractmethod
    async def get(self, project_id: int) -> BriefRecord | None:
        ...


class AssetRepository(ABC):
    """项目素材仓储端口（DIP）：元数据落库，字节走 AssetStore。"""

    @abstractmethod
    async def create(self, *, project_id: int, kind: AssetKind, url: str) -> AssetRecord:
        ...

    @abstractmethod
    async def get_many(self, asset_ids: Sequence[int]) -> list[AssetRecord]:
        ...

    @abstractmethod
    async def list(self, *, project_id: int) -> list[AssetRecord]:
        ...
