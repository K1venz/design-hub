from dataclasses import dataclass

from design_hub.domain.enums import AssetKind
from design_hub.domain.errors import NotFoundError
from design_hub.domain.models import AssetRecord
from design_hub.ports.asset_store import AssetStore
from design_hub.ports.repositories import AssetRepository, ProjectRepository


@dataclass
class AssetService:
    """项目素材用例（SRP）：字节落 AssetStore、元数据落 AssetRepository（DIP）。"""

    assets: AssetRepository
    store: AssetStore
    projects: ProjectRepository

    async def upload(
        self, project_id: int, *, kind: AssetKind, data: bytes, suffix: str = ".png"
    ) -> AssetRecord:
        await self._require_project(project_id)
        if not data:
            raise ValueError("素材文件为空")
        url = await self.store.save(data, suffix=suffix)
        return await self.assets.create(project_id=project_id, kind=kind, url=url)

    async def list(self, project_id: int) -> list[AssetRecord]:
        await self._require_project(project_id)
        return await self.assets.list(project_id=project_id)

    async def _require_project(self, project_id: int) -> None:
        if await self.projects.get(project_id) is None:
            raise NotFoundError(f"项目 {project_id} 不存在")
