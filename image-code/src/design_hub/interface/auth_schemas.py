"""认证 / 用户管理 HTTP schema（ISSUE-0015：自建邮箱密码，替换 OAuth）。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from design_hub.domain.enums import Role
from design_hub.domain.models import AuthUser
from design_hub.ports.user_repository import UserAccount


class RegisterRequest(BaseModel):
    email: EmailStr
    # password = base64(RSA-OAEP-SHA256 密文，ISSUE-0058)；明文长度(≥8)校验在解密后 AccountService
    password: str = Field(min_length=1)
    name: str = Field(min_length=1)


class RegisterVerificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    challenge_id: str = Field(min_length=32, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    code: str = Field(pattern=r"^[0-9]{6}$")


class RegisterResendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    challenge_id: str = Field(min_length=32, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


class RegistrationAcknowledgement(BaseModel):
    message: str
    challenge_id: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)  # base64(RSA-OAEP-SHA256 密文，ISSUE-0058)


class LoginResponse(BaseModel):
    jwt: str
    role: Role
    name: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    message: str


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6)
    # password = base64(RSA-OAEP-SHA256 密文)；明文长度校验在解密后 AccountService
    password: str = Field(min_length=1)


class ResetPasswordResponse(BaseModel):
    message: str


class PubKeyResponse(BaseModel):
    """GET /auth/pubkey（ISSUE-0058）：SPKI PEM 公钥，前端 WebCrypto 加密密码用。"""

    public_key: str  # -----BEGIN PUBLIC KEY----- ...（SPKI，与前端 #1017 契约字段名对齐）


class MeResponse(BaseModel):
    user_id: str
    name: str
    role: Role
    dept: str | None

    @classmethod
    def of(cls, u: AuthUser) -> "MeResponse":
        return cls(user_id=u.user_id, name=u.name, role=u.role, dept=u.dept)


class UserOut(BaseModel):
    """用户管理列表项。**不含 password_hash**。"""

    id: int
    email: str
    name: str
    role: Role
    enabled: bool
    disabled_at: datetime | None
    disabled_reason: str | None
    created_at: datetime

    @classmethod
    def of(cls, a: UserAccount) -> "UserOut":
        return cls(
            id=a.id,
            email=a.email,
            name=a.name,
            role=a.role,
            enabled=a.enabled,
            disabled_at=a.disabled_at,
            disabled_reason=a.disabled_reason,
            created_at=a.created_at,
        )


class RoleUpdate(BaseModel):
    role: Role


class UserStatusUpdate(BaseModel):
    enabled: bool
    reason: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def validate_reason(self) -> "UserStatusUpdate":
        self.reason = self.reason.strip()
        if not self.enabled and not self.reason:
            raise ValueError("停用用户时必须填写原因")
        return self
