"""项目级任务/候选图列举用例（ISSUE-0012）。纯读，委托 ProjectCatalogQuery（DIP）。"""

from dataclasses import dataclass

from design_hub.ports.project_catalog import ProjectCatalogQuery, ProjectImage, ProjectJob


@dataclass
class ProjectCatalogService:
    catalog: ProjectCatalogQuery

    async def jobs(self, project_id: int, *, round_no: int | None = None) -> list[ProjectJob]:
        return await self.catalog.jobs(project_id, round_no=round_no)

    async def images(
        self, project_id: int, *, round_no: int | None = None, kept: bool | None = None
    ) -> list[ProjectImage]:
        return await self.catalog.images(project_id, round_no=round_no, kept=kept)
