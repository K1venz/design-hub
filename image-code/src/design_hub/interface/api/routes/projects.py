from fastapi import APIRouter, HTTPException

from design_hub.interface.api.project_deps import ProjectServiceDep
from design_hub.interface.project_schemas import (
    ProjectCreate,
    ProjectOut,
    ProjectStatusUpdate,
)

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectOut)
async def create_project(body: ProjectCreate, svc: ProjectServiceDep) -> ProjectOut:
    return ProjectOut.of(await svc.create(customer_id=body.customer_id, name=body.name))


@router.get("", response_model=list[ProjectOut])
async def list_projects(svc: ProjectServiceDep, customer_id: int | None = None) -> list[ProjectOut]:
    return [ProjectOut.of(r) for r in await svc.list(customer_id=customer_id)]


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(project_id: int, svc: ProjectServiceDep) -> ProjectOut:
    record = await svc.get(project_id)
    if record is None:
        raise HTTPException(status_code=404, detail="project not found")
    return ProjectOut.of(record)


@router.put("/{project_id}/status", response_model=ProjectOut)
async def update_status(
    project_id: int, body: ProjectStatusUpdate, svc: ProjectServiceDep
) -> ProjectOut:
    # 非法流转/项目不存在 → ProjectService 抛 DomainError，由边界统一映射
    return ProjectOut.of(await svc.transition(project_id, body.status))
