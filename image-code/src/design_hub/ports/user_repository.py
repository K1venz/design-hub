"""用户账户仓储端口（DIP，ISSUE-0015）。app_user 表读写抽象。"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from design_hub.domain.enums import Role


@dataclass(frozen=True)
class UserAccount:
    """用户账户读模型。password_hash 仅供 login 校验，**绝不外泄到 HTTP**（UserOut 不含）。"""

    id: int
    email: str
    name: str
    role: Role
    created_at: datetime
    password_hash: str
    enabled: bool = True
    disabled_at: datetime | None = None
    disabled_by: int | None = None
    disabled_reason: str | None = None


class UserRepository(ABC):
    @abstractmethod
    async def get_by_email(self, email: str) -> UserAccount | None:
        ...

    @abstractmethod
    async def get_by_id(self, user_id: int) -> UserAccount | None:
        ...

    @abstractmethod
    async def add(self, *, email: str, password_hash: str, name: str, role: Role) -> UserAccount:
        ...

    @abstractmethod
    async def set_role_with_audit(
        self,
        *,
        actor_id: int,
        user_id: int,
        role: Role,
    ) -> UserAccount:
        ...

    @abstractmethod
    async def set_status_with_audit(
        self,
        *,
        actor_id: int,
        user_id: int,
        enabled: bool,
        reason: str,
    ) -> UserAccount:
        ...

    @abstractmethod
    async def list_all(self) -> list[UserAccount]:
        ...
