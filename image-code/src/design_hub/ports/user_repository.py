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
    async def set_role(self, user_id: int, role: Role) -> UserAccount:
        """改角色；user_id 不存在 → NotFoundError（边界映射 404）。"""
        ...

    @abstractmethod
    async def list_all(self) -> list[UserAccount]:
        ...

    @abstractmethod
    async def count_by_role(self, role: Role) -> int:
        ...
