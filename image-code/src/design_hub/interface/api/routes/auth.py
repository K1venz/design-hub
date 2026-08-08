"""认证路由（ISSUE-0015：自建邮箱密码，替换 OAuth）。

/auth/register、/auth/login、/auth/forgot-password、/auth/reset-password 公开；
/me 需登录。错误经边界映射：重复邮箱→409、弱密码/格式→400、登录失败→401。
"""

from fastapi import APIRouter

from design_hub.interface.api.deps import (
    AccountServiceDep,
    CurrentUserDep,
    SecretCipherDep,
)
from design_hub.interface.auth_schemas import (
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    LoginResponse,
    MeResponse,
    PubKeyResponse,
    RegisterRequest,
    ResetPasswordRequest,
    ResetPasswordResponse,
)

router = APIRouter(tags=["auth"])


@router.get("/auth/pubkey", response_model=PubKeyResponse)
async def pubkey(cipher: SecretCipherDep) -> PubKeyResponse:
    """密码加密公钥（ISSUE-0058，公开、可缓存）：前端 WebCrypto 用它加密密码。"""
    return PubKeyResponse(public_key=cipher.public_key_pem())


@router.post("/auth/register", response_model=LoginResponse)
async def register(
    body: RegisterRequest, svc: AccountServiceDep, cipher: SecretCipherDep
) -> LoginResponse:
    password = _decrypt_password(cipher, body.password)
    token, user = await svc.register(email=body.email, password=password, name=body.name)
    return LoginResponse(jwt=token, role=user.role, name=user.name)


@router.post("/auth/login", response_model=LoginResponse)
async def login(
    body: LoginRequest, svc: AccountServiceDep, cipher: SecretCipherDep
) -> LoginResponse:
    password = _decrypt_password(cipher, body.password)
    token, user = await svc.login(email=body.email, password=password)
    return LoginResponse(jwt=token, role=user.role, name=user.name)


@router.post("/auth/forgot-password", response_model=ForgotPasswordResponse)
async def forgot_password(
    body: ForgotPasswordRequest, svc: AccountServiceDep
) -> ForgotPasswordResponse:
    """请求重置验证码：无论邮箱是否存在都返回同一成功文案（防枚举）。"""
    message = await svc.request_password_reset(email=body.email)
    return ForgotPasswordResponse(message=message)


@router.post("/auth/reset-password", response_model=ResetPasswordResponse)
async def reset_password(
    body: ResetPasswordRequest, svc: AccountServiceDep, cipher: SecretCipherDep
) -> ResetPasswordResponse:
    """校验验证码并设置新密码（密码仍走 RSA 密文传输）。"""
    password = _decrypt_password(cipher, body.password)
    await svc.reset_password(email=body.email, code=body.code, password=password)
    return ResetPasswordResponse(message="密码已重置，请使用新密码登录")


@router.get("/me", response_model=MeResponse)
async def me(user: CurrentUserDep) -> MeResponse:
    """当前用户（需 Bearer JWT）。无/坏令牌→401。"""
    return MeResponse.of(user)


def _decrypt_password(cipher: SecretCipherDep, ciphertext: str) -> str:
    try:
        return cipher.decrypt(ciphertext)
    except ValueError:
        raise ValueError("密码解密失败，请刷新页面后重试") from None
