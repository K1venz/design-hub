from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from design_hub.domain.errors import NotFoundError
from design_hub.domain.models import RevisionRecord
from design_hub.ports.repositories import ProjectRepository
from design_hub.ports.revision_repository import RevisionRepository


@dataclass
class RevisionService:
    """改稿单用例（SRP）：开单/列单/加条目/逐条勾选。依赖端口（DIP）。"""

    revisions: RevisionRepository
    projects: ProjectRepository

    async def open(
        self, project_id: int, *, round_no: int | None = None, deadline: datetime | None = None
    ) -> RevisionRecord:
        project = await self.projects.get(project_id)
        if project is None:
            raise NotFoundError(f"项目 {project_id} 不存在")
        rn = round_no if round_no is not None else project.current_round
        return await self.revisions.create(project_id=project_id, round_no=rn, deadline=deadline)

    async def list_for_project(self, project_id: int) -> list[RevisionRecord]:
        if await self.projects.get(project_id) is None:
            raise NotFoundError(f"项目 {project_id} 不存在")
        return await self.revisions.list_by_project(project_id)

    async def add_item(
        self, revision_id: int, *, text: str, related_image_id: int | None = None
    ) -> RevisionRecord:
        if not text.strip():
            raise ValueError("改稿条目内容不能为空")
        return await self.revisions.add_item(
            revision_id, text=text, related_image_id=related_image_id
        )

    async def toggle_item(self, revision_id: int, seq: int, *, done: bool) -> RevisionRecord:
        return await self.revisions.set_item_done(revision_id, seq, done=done)
