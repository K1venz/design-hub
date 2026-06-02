"""用户管理后台用例（ISSUE-0015，仅管理者）。"""

from dataclasses import dataclass

from design_hub.domain.enums import Role
from design_hub.domain.errors import DomainError
from design_hub.ports.user_repository import UserAccount, UserRepository


@dataclass
class UserAdminService:
    users: UserRepository

    async def list_users(self) -> list[UserAccount]:
        return await self.users.list_all()

    async def set_role(self, user_id: int, role: Role) -> UserAccount:
        # 保护：系统至少保留 1 个管理者，最后一个管理者不可降级
        if role is Role.DESIGNER:
            current = await self.users.get_by_id(user_id)
            if (
                current is not None
                and current.role is Role.MANAGER
                and await self.users.count_by_role(Role.MANAGER) <= 1
            ):
                raise DomainError("不能降级最后一个管理者")  # 409
        # user_id 不存在 → 仓储抛 NotFoundError(404)
        return await self.users.set_role(user_id, role)
