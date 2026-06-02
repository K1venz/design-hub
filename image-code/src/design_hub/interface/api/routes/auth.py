from fastapi import APIRouter

from design_hub.interface.api.deps import AuthServiceDep, CurrentUserDep
from design_hub.interface.auth_schemas import LoginRequest, LoginResponse, MeResponse

# 无前缀：/auth/{provider}/callback 公开 + /me 需登录（在 asgi 以无 include 级依赖挂载）
router = APIRouter(tags=["auth"])


@router.post("/auth/{provider}/callback", response_model=LoginResponse)
async def oauth_callback(
    provider: str, body: LoginRequest, svc: AuthServiceDep
) -> LoginResponse:
    """OAuth 回调换 JWT（mock：provider 暂不分流，统一走 MockOAuthClient）。

    部门不许→PermissionDenied 403；授权失败→AuthenticationError 401（边界映射）。
    """
    token, user = await svc.login(body.code)
    return LoginResponse(jwt=token, role=user.role, name=user.name)


@router.get("/me", response_model=MeResponse)
async def me(user: CurrentUserDep) -> MeResponse:
    """当前用户（需 Bearer JWT）。无/坏令牌→401。"""
    return MeResponse.of(user)
