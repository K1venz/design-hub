"""用户管理后台路由（ISSUE-0015，仅管理者；鉴权在 asgi include 级挂 manager_only）。"""

from fastapi import APIRouter

from design_hub.interface.api.deps import CurrentManagerDep, UserAdminServiceDep
from design_hub.interface.auth_schemas import RoleUpdate, UserOut, UserStatusUpdate

router = APIRouter(prefix="/admin", tags=["admin"])


@router.put("/users/{user_id}/role", response_model=UserOut)
async def set_user_role(
    user_id: int,
    body: RoleUpdate,
    manager: CurrentManagerDep,
    svc: UserAdminServiceDep,
) -> UserOut:
    return UserOut.of(
        await svc.set_role(
            actor_id=int(manager.user_id),
            user_id=user_id,
            role=body.role,
        )
    )


@router.put("/users/{user_id}/status", response_model=UserOut)
async def set_user_status(
    user_id: int,
    body: UserStatusUpdate,
    manager: CurrentManagerDep,
    svc: UserAdminServiceDep,
) -> UserOut:
    return UserOut.of(
        await svc.set_status(
            actor_id=int(manager.user_id),
            user_id=user_id,
            enabled=body.enabled,
            reason=body.reason,
        )
    )
