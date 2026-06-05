"""项目级任务/候选图列举路由（ISSUE-0012，薄）。

GET /projects/{id}/jobs[?round_no=]        列项目下出图任务（选稿按任务分组）
GET /projects/{id}/images[?round_no=&kept=]  列项目下候选图（导出/交付勾选、保留总览）
独立路由文件，不动 WP-A 的 projects.py；与其同 /projects 前缀由 FastAPI 合并。
"""

from fastapi import APIRouter

from design_hub.interface.api.deps import MediaSignerDep
from design_hub.interface.api.project_catalog_deps import ProjectCatalogServiceDep
from design_hub.interface.project_catalog_schemas import ProjectImageOut, ProjectJobOut

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("/{project_id}/jobs", response_model=list[ProjectJobOut])
async def list_project_jobs(
    project_id: int, svc: ProjectCatalogServiceDep, round_no: int | None = None
) -> list[ProjectJobOut]:
    return [ProjectJobOut.of(j) for j in await svc.jobs(project_id, round_no=round_no)]


@router.get("/{project_id}/images", response_model=list[ProjectImageOut])
async def list_project_images(
    project_id: int,
    svc: ProjectCatalogServiceDep,
    signer: MediaSignerDep,
    round_no: int | None = None,
    kept: bool | None = None,
) -> list[ProjectImageOut]:
    return [
        ProjectImageOut.of(i, signer)
        for i in await svc.images(project_id, round_no=round_no, kept=kept)
    ]
