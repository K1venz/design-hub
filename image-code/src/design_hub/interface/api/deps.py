from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Header, Request, Response

from design_hub.application.admin.runtime_log_service import RuntimeLogService
from design_hub.application.admin.user_admin_service import UserAdminService
from design_hub.application.auth.account_service import AccountService
from design_hub.domain.enums import Role
from design_hub.domain.errors import AuthenticationError, PermissionDenied
from design_hub.domain.models import AuthUser
from design_hub.ports.auth import TokenService
from design_hub.ports.media_url_signer import MediaUrlSigner
from design_hub.ports.secret_cipher import SecretCipher
from design_hub.ports.user_repository import UserRepository


def get_media_signer(request: Request) -> MediaUrlSigner:
    signer = request.app.state.media_signer
    assert isinstance(signer, MediaUrlSigner)
    return signer


def get_token_service(request: Request) -> TokenService:
    svc = request.app.state.token_service
    assert isinstance(svc, TokenService)
    return svc


def get_account_service(request: Request) -> AccountService:
    svc = request.app.state.account_service
    assert isinstance(svc, AccountService)
    return svc


def get_secret_cipher(request: Request) -> SecretCipher:
    cipher = request.app.state.secret_cipher
    assert isinstance(cipher, SecretCipher)
    return cipher


def get_user_admin_service(request: Request) -> UserAdminService:
    svc = request.app.state.user_admin_service
    assert isinstance(svc, UserAdminService)
    return svc


def get_user_repository(request: Request) -> UserRepository:
    repo = request.app.state.user_repository
    assert isinstance(repo, UserRepository)
    return repo


def get_runtime_log_service(request: Request) -> RuntimeLogService:
    service = request.app.state.runtime_log_service
    assert isinstance(service, RuntimeLogService)
    return service


async def _current_database_user(
    request: Request,
    token_user: AuthUser,
) -> AuthUser:
    try:
        user_id = int(token_user.user_id)
    except ValueError as exc:
        raise AuthenticationError("令牌用户 ID 无效") from exc
    account = await get_user_repository(request).get_by_id(user_id)
    if account is None or not account.enabled:
        raise AuthenticationError("账号已停用或不存在")
    return AuthUser(
        user_id=str(account.id),
        name=account.name,
        role=account.role,
        dept=None,
    )


async def get_current_user(
    request: Request,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> AuthUser:
    """解析 Bearer JWT → AuthUser；缺/坏令牌抛 AuthenticationError（边界映射 401）。

    滑动续期（ISSUE-0058）：令牌过半衰期则把新 24h 令牌放响应头 X-Renewed-Token（前端无感换）；
    exp 已过仍走 verify 抛 401 原路（不续过期令牌）。
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthenticationError("缺少 Bearer 令牌")
    token = authorization.split(" ", 1)[1].strip()
    svc = get_token_service(request)
    token_user = svc.verify(token)  # 缺/坏/过期 → 401
    user = await _current_database_user(request, token_user)
    renewed = svc.renew_if_stale(token, user)
    if renewed is not None:
        response.headers["X-Renewed-Token"] = renewed
    return user


async def get_current_user_sse(
    request: Request,
    access_token: str | None = None,
    authorization: Annotated[str | None, Header()] = None,
) -> AuthUser:
    """SSE 专用鉴权（ISSUE-0011）：原生 EventSource 不能带 Bearer 头，故接受
    `?access_token=<JWT>` query 传参（也兼容 Bearer 头）。仅 SSE 端点放宽，其余仍走头。
    """
    token = access_token
    if not token and authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise AuthenticationError("缺少令牌（SSE 经 ?access_token= 或 Bearer 头）")
    token_user = get_token_service(request).verify(token)
    return await _current_database_user(request, token_user)


AccountServiceDep = Annotated[AccountService, Depends(get_account_service)]
SecretCipherDep = Annotated[SecretCipher, Depends(get_secret_cipher)]
UserAdminServiceDep = Annotated[UserAdminService, Depends(get_user_admin_service)]
CurrentUserDep = Annotated[AuthUser, Depends(get_current_user)]
CurrentUserSseDep = Annotated[AuthUser, Depends(get_current_user_sse)]
MediaSignerDep = Annotated[MediaUrlSigner, Depends(get_media_signer)]
RuntimeLogServiceDep = Annotated[
    RuntimeLogService,
    Depends(get_runtime_log_service),
]


def require_role(*roles: Role) -> Callable[[AuthUser], Awaitable[AuthUser]]:
    """生成「要求指定角色」的依赖；角色不符抛 PermissionDenied（边界映射 403）。"""

    async def _require(user: CurrentUserDep) -> AuthUser:
        if user.role not in roles:
            allowed = "/".join(r.value for r in roles)
            raise PermissionDenied(f"需要角色：{allowed}（当前：{user.role.value}）")
        return user

    return _require


CurrentManagerDep = Annotated[AuthUser, Depends(require_role(Role.MANAGER))]
