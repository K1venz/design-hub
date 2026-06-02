from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Header, Request

from design_hub.application.admin.user_admin_service import UserAdminService
from design_hub.application.auth.account_service import AccountService
from design_hub.composition import Engine
from design_hub.domain.enums import Role
from design_hub.domain.errors import AuthenticationError, PermissionDenied
from design_hub.domain.models import AuthUser
from design_hub.ports.auth import TokenService


def get_engine(request: Request) -> Engine:
    engine = request.app.state.engine
    assert isinstance(engine, Engine)
    return engine


def get_token_service(request: Request) -> TokenService:
    svc = request.app.state.token_service
    assert isinstance(svc, TokenService)
    return svc


def get_account_service(request: Request) -> AccountService:
    svc = request.app.state.account_service
    assert isinstance(svc, AccountService)
    return svc


def get_user_admin_service(request: Request) -> UserAdminService:
    svc = request.app.state.user_admin_service
    assert isinstance(svc, UserAdminService)
    return svc


async def get_current_user(
    request: Request, authorization: Annotated[str | None, Header()] = None
) -> AuthUser:
    """解析 Bearer JWT → AuthUser；缺/坏令牌抛 AuthenticationError（边界映射 401）。"""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthenticationError("缺少 Bearer 令牌")
    token = authorization.split(" ", 1)[1].strip()
    return get_token_service(request).verify(token)


EngineDep = Annotated[Engine, Depends(get_engine)]
UserIdDep = Annotated[str, Header(alias="X-User-Id")]
AccountServiceDep = Annotated[AccountService, Depends(get_account_service)]
UserAdminServiceDep = Annotated[UserAdminService, Depends(get_user_admin_service)]
CurrentUserDep = Annotated[AuthUser, Depends(get_current_user)]


def require_role(*roles: Role) -> Callable[[AuthUser], Awaitable[AuthUser]]:
    """生成「要求指定角色」的依赖；角色不符抛 PermissionDenied（边界映射 403）。"""

    async def _require(user: CurrentUserDep) -> AuthUser:
        if user.role not in roles:
            allowed = "/".join(r.value for r in roles)
            raise PermissionDenied(f"需要角色：{allowed}（当前：{user.role.value}）")
        return user

    return _require
