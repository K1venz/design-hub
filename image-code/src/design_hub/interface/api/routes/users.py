"""用户管理后台路由（ISSUE-0015，仅管理者；鉴权在 asgi include 级挂 manager_only）。"""

from fastapi import APIRouter

from design_hub.interface.api.deps import UserAdminServiceDep
from design_hub.interface.auth_schemas import RoleUpdate, UserOut

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=list[UserOut])
async def list_users(svc: UserAdminServiceDep) -> list[UserOut]:
    return [UserOut.of(a) for a in await svc.list_users()]


@router.put("/users/{user_id}/role", response_model=UserOut)
async def set_user_role(user_id: int, body: RoleUpdate, svc: UserAdminServiceDep) -> UserOut:
    # user 不存在→404；降级最后一个管理者→409（边界映射）
    return UserOut.of(await svc.set_role(user_id, body.role))
