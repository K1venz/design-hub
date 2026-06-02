"""认证 / 用户管理 HTTP schema（ISSUE-0015：自建邮箱密码，替换 OAuth）。"""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from design_hub.domain.enums import Role
from design_hub.domain.models import AuthUser
from design_hub.ports.user_repository import UserAccount


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    name: str = Field(min_length=1)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class LoginResponse(BaseModel):
    jwt: str
    role: Role
    name: str


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
    created_at: datetime

    @classmethod
    def of(cls, a: UserAccount) -> "UserOut":
        return cls(id=a.id, email=a.email, name=a.name, role=a.role, created_at=a.created_at)


class RoleUpdate(BaseModel):
    role: Role
