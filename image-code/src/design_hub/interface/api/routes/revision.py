from fastapi import APIRouter

from design_hub.interface.api.revision_deps import RevisionServiceDep
from design_hub.interface.revision_schemas import (
    AddItemRequest,
    RevisionOpenRequest,
    RevisionOut,
    ToggleItemRequest,
)

# 跨 /projects 与 /revisions 两组路径，故不设统一前缀；薄控制器，错误经边界统一映射
router = APIRouter(tags=["revision"])


@router.post("/projects/{project_id}/revisions", response_model=RevisionOut)
async def open_revision(
    project_id: int, body: RevisionOpenRequest, svc: RevisionServiceDep
) -> RevisionOut:
    rev = await svc.open(project_id, round_no=body.round_no, deadline=body.deadline)
    return RevisionOut.of(rev)


@router.get("/projects/{project_id}/revisions", response_model=list[RevisionOut])
async def list_revisions(project_id: int, svc: RevisionServiceDep) -> list[RevisionOut]:
    return [RevisionOut.of(r) for r in await svc.list_for_project(project_id)]


@router.post("/revisions/{revision_id}/items", response_model=RevisionOut)
async def add_item(
    revision_id: int, body: AddItemRequest, svc: RevisionServiceDep
) -> RevisionOut:
    rev = await svc.add_item(revision_id, text=body.text, related_image_id=body.related_image_id)
    return RevisionOut.of(rev)


@router.put("/revisions/{revision_id}/items/{seq}", response_model=RevisionOut)
async def toggle_item(
    revision_id: int, seq: int, body: ToggleItemRequest, svc: RevisionServiceDep
) -> RevisionOut:
    return RevisionOut.of(await svc.toggle_item(revision_id, seq, done=body.done))
