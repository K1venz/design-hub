from datetime import datetime

from fastapi import APIRouter

from design_hub.domain.admin import ModerationStatus, ShowcaseStatus
from design_hub.domain.enums import Role
from design_hub.interface.admin_console_schemas import (
    AdminAuditEntryOut,
    AdminImageSummaryOut,
    AdminJobDetailOut,
    AdminJobImageOut,
    AdminJobSummaryOut,
    AdminOverviewOut,
    AdminUserDetailOut,
    AdminUserSummaryOut,
    ImageModerationUpdate,
    ImageShowcaseStateOut,
    ImageShowcaseUpdate,
    ModelCallDetailOut,
    ModelCallSummaryListOut,
    ModelCallSummaryOut,
    PageOut,
)
from design_hub.interface.api.admin_deps import AdminConsoleServiceDep
from design_hub.interface.api.deps import (
    CurrentManagerDep,
    MediaSignerDep,
    ShowcaseServiceDep,
)
from design_hub.ports.admin_console import (
    AdminAuditFilter,
    AdminImageFilter,
    AdminJobFilter,
    ModelCallFilter,
)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/overview", response_model=AdminOverviewOut)
async def overview(
    manager: CurrentManagerDep,
    service: AdminConsoleServiceDep,
    start: datetime | None = None,
    end: datetime | None = None,
) -> AdminOverviewOut:
    del manager
    date_range = service.date_range(
        start=start,
        end=end,
        default_days=7,
    )
    assert date_range is not None
    return AdminOverviewOut.of(await service.overview(date_range))


@router.get("/users", response_model=PageOut[AdminUserSummaryOut])
async def list_users(
    manager: CurrentManagerDep,
    service: AdminConsoleServiceDep,
    q: str | None = None,
    role: Role | None = None,
    enabled: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> PageOut[AdminUserSummaryOut]:
    del manager
    page = await service.list_users(
        q=q,
        role=role,
        enabled=enabled,
        limit=limit,
        offset=offset,
    )
    return PageOut.of(
        page,
        [AdminUserSummaryOut.of(item) for item in page.items],
    )


@router.get("/users/{user_id}", response_model=AdminUserDetailOut)
async def get_user(
    user_id: int,
    manager: CurrentManagerDep,
    service: AdminConsoleServiceDep,
) -> AdminUserDetailOut:
    del manager
    return AdminUserDetailOut.from_detail(await service.get_user(user_id))


@router.get("/jobs", response_model=PageOut[AdminJobSummaryOut])
async def list_jobs(
    manager: CurrentManagerDep,
    service: AdminConsoleServiceDep,
    signer: MediaSignerDep,
    user_id: int | None = None,
    status: str | None = None,
    model: str | None = None,
    operation_type: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> PageOut[AdminJobSummaryOut]:
    del manager
    page = await service.list_jobs(
        AdminJobFilter(
            user_id=user_id,
            status=status,
            model=model,
            operation_type=operation_type,
            date_range=service.date_range(start=start, end=end),
        ),
        limit=limit,
        offset=offset,
    )
    return PageOut.of(
        page,
        [AdminJobSummaryOut.of(item, signer) for item in page.items],
    )


@router.get("/jobs/{job_id}", response_model=AdminJobDetailOut)
async def get_job(
    job_id: str,
    manager: CurrentManagerDep,
    service: AdminConsoleServiceDep,
    signer: MediaSignerDep,
) -> AdminJobDetailOut:
    del manager
    return AdminJobDetailOut.from_detail(
        await service.get_job(job_id),
        signer,
    )


@router.get("/images", response_model=PageOut[AdminImageSummaryOut])
async def list_images(
    manager: CurrentManagerDep,
    service: AdminConsoleServiceDep,
    signer: MediaSignerDep,
    user_id: int | None = None,
    model: str | None = None,
    operation_type: str | None = None,
    status: str | None = None,
    moderation_status: ModerationStatus | None = None,
    showcase_status: ShowcaseStatus | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> PageOut[AdminImageSummaryOut]:
    del manager
    page = await service.list_images(
        AdminImageFilter(
            user_id=user_id,
            model=model,
            operation_type=operation_type,
            status=status,
            moderation_status=(
                moderation_status.value
                if moderation_status is not None
                else None
            ),
            showcase_status=(
                showcase_status.value if showcase_status is not None else None
            ),
            date_range=service.date_range(start=start, end=end),
        ),
        limit=limit,
        offset=offset,
    )
    return PageOut.of(
        page,
        [AdminImageSummaryOut.of(item, signer) for item in page.items],
    )


@router.put(
    "/images/{image_id}/moderation",
    response_model=AdminJobImageOut,
)
async def set_image_moderation(
    image_id: int,
    body: ImageModerationUpdate,
    manager: CurrentManagerDep,
    service: AdminConsoleServiceDep,
    signer: MediaSignerDep,
) -> AdminJobImageOut:
    image = await service.set_image_moderation(
        actor_id=int(manager.user_id),
        image_id=image_id,
        status=body.status,
        reason=body.reason,
        note=body.note,
    )
    return AdminJobImageOut.of(image, signer)


@router.put(
    "/images/{image_id}/showcase",
    response_model=ImageShowcaseStateOut,
)
async def set_image_showcase(
    image_id: int,
    body: ImageShowcaseUpdate,
    manager: CurrentManagerDep,
    service: ShowcaseServiceDep,
) -> ImageShowcaseStateOut:
    result = await service.set_publication(
        actor_id=int(manager.user_id),
        image_id=image_id,
        is_public=body.is_public,
        download_allowed=body.download_allowed,
    )
    return ImageShowcaseStateOut.model_validate(result, from_attributes=True)


@router.get(
    "/model-calls/summary",
    response_model=ModelCallSummaryListOut,
)
async def summarize_model_calls(
    manager: CurrentManagerDep,
    service: AdminConsoleServiceDep,
    user_id: int | None = None,
    provider: str | None = None,
    model: str | None = None,
    modality: str | None = None,
    operation_type: str | None = None,
    status: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> ModelCallSummaryListOut:
    del manager
    rows = await service.summarize_model_calls(
        ModelCallFilter(
            user_id=user_id,
            provider=provider,
            model=model,
            modality=modality,
            operation_type=operation_type,
            status=status,
            date_range=service.date_range(
                start=start,
                end=end,
                default_days=7,
            ),
        )
    )
    return ModelCallSummaryListOut(
        models=[ModelCallSummaryOut.of(row) for row in rows]
    )


@router.get("/model-calls", response_model=PageOut[ModelCallDetailOut])
async def list_model_calls(
    manager: CurrentManagerDep,
    service: AdminConsoleServiceDep,
    user_id: int | None = None,
    provider: str | None = None,
    model: str | None = None,
    modality: str | None = None,
    operation_type: str | None = None,
    status: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> PageOut[ModelCallDetailOut]:
    del manager
    page = await service.list_model_calls(
        ModelCallFilter(
            user_id=user_id,
            provider=provider,
            model=model,
            modality=modality,
            operation_type=operation_type,
            status=status,
            date_range=service.date_range(start=start, end=end),
        ),
        limit=limit,
        offset=offset,
    )
    return PageOut.of(
        page,
        [ModelCallDetailOut.of(item) for item in page.items],
    )


@router.get("/audit-logs", response_model=PageOut[AdminAuditEntryOut])
async def list_audit_logs(
    manager: CurrentManagerDep,
    service: AdminConsoleServiceDep,
    actor_user_id: int | None = None,
    action: str | None = None,
    target_type: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> PageOut[AdminAuditEntryOut]:
    del manager
    page = await service.list_audit_logs(
        AdminAuditFilter(
            actor_user_id=actor_user_id,
            action=action,
            target_type=target_type,
            date_range=service.date_range(start=start, end=end),
        ),
        limit=limit,
        offset=offset,
    )
    return PageOut.of(
        page,
        [AdminAuditEntryOut.of(item) for item in page.items],
    )
