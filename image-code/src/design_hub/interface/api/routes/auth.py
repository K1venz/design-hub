"""认证路由（ISSUE-0015：自建邮箱密码，替换 OAuth）。

/auth/register、/auth/login 公开；/me 需登录。错误经边界映射：
重复邮箱→409、弱密码/格式→400、登录失败→401。
"""

from fastapi import APIRouter

from design_hub.interface.api.deps import AccountServiceDep, CurrentUserDep
from design_hub.interface.auth_schemas import (
    LoginRequest,
    LoginResponse,
    MeResponse,
    RegisterRequest,
)

router = APIRouter(tags=["auth"])


@router.post("/auth/register", response_model=LoginResponse)
async def register(body: RegisterRequest, svc: AccountServiceDep) -> LoginResponse:
    token, user = await svc.register(email=body.email, password=body.password, name=body.name)
    return LoginResponse(jwt=token, role=user.role, name=user.name)


@router.post("/auth/login", response_model=LoginResponse)
async def login(body: LoginRequest, svc: AccountServiceDep) -> LoginResponse:
    token, user = await svc.login(email=body.email, password=body.password)
    return LoginResponse(jwt=token, role=user.role, name=user.name)


@router.get("/me", response_model=MeResponse)
async def me(user: CurrentUserDep) -> MeResponse:
    """当前用户（需 Bearer JWT）。无/坏令牌→401。"""
    return MeResponse.of(user)
