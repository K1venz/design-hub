from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from design_hub.domain.errors import NotFoundError
from design_hub.domain.models import BriefRecord
from design_hub.ports.repositories import BriefRepository, ProjectRepository


@dataclass
class BriefService:
    """标准化需求单用例（SRP）：存/取 PRD 8 字段，校验项目存在（DIP）。"""

    briefs: BriefRepository
    projects: ProjectRepository

    async def put(
        self,
        project_id: int,
        *,
        material_types: Sequence[str] = (),
        sizes: Sequence[str] = (),
        styles: Sequence[str] = (),
        resolution: str | None = None,
        bleed: str | None = None,
        copy_text: str | None = None,
        taboo: str | None = None,
        delivery: Mapping[str, Any] | None = None,
    ) -> BriefRecord:
        await self._require_project(project_id)
        return await self.briefs.upsert(
            project_id=project_id,
            material_types=material_types,
            sizes=sizes,
            styles=styles,
            resolution=resolution,
            bleed=bleed,
            copy_text=copy_text,
            taboo=taboo,
            delivery=delivery,
        )

    async def get(self, project_id: int) -> BriefRecord:
        await self._require_project(project_id)
        brief = await self.briefs.get(project_id)
        if brief is None:
            raise NotFoundError(f"项目 {project_id} 尚无需求单")
        return brief

    async def _require_project(self, project_id: int) -> None:
        if await self.projects.get(project_id) is None:
            raise NotFoundError(f"项目 {project_id} 不存在")
