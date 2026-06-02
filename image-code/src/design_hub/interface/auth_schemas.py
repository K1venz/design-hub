from pydantic import BaseModel, Field

from design_hub.domain.enums import Role
from design_hub.domain.models import AuthUser


class LoginRequest(BaseModel):
    code: str = Field(min_length=1)


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
