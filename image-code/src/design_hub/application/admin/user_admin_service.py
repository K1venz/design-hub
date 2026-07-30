"""Manager user-control use cases."""

from dataclasses import dataclass

from design_hub.domain.enums import Role
from design_hub.ports.user_repository import UserAccount, UserRepository


@dataclass
class UserAdminService:
    users: UserRepository

    async def list_users(self) -> list[UserAccount]:
        return await self.users.list_all()

    async def set_role(
        self,
        *,
        actor_id: int,
        user_id: int,
        role: Role,
    ) -> UserAccount:
        return await self.users.set_role_with_audit(
            actor_id=actor_id,
            user_id=user_id,
            role=role,
        )

    async def set_status(
        self,
        *,
        actor_id: int,
        user_id: int,
        enabled: bool,
        reason: str,
    ) -> UserAccount:
        normalized_reason = reason.strip()
        if not enabled and not normalized_reason:
            raise ValueError("停用用户时必须填写原因")
        return await self.users.set_status_with_audit(
            actor_id=actor_id,
            user_id=user_id,
            enabled=enabled,
            reason=normalized_reason,
        )
