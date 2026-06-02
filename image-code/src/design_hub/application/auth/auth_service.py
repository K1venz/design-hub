from dataclasses import dataclass

from design_hub.domain.enums import Role
from design_hub.domain.errors import PermissionDenied
from design_hub.domain.models import AuthUser
from design_hub.ports.auth import OAuthClient, TokenService

# PRD §6.3.3 部门→角色映射；未列入的部门一律拒绝（fail-fast）
_DEPT_ROLE: dict[str, Role] = {
    "设计部": Role.DESIGNER,
    "管理层": Role.MANAGER,
    "负责人": Role.MANAGER,
}


def role_for_dept(dept: str) -> Role:
    role = _DEPT_ROLE.get(dept)
    if role is None:
        raise PermissionDenied(f"部门「{dept}」无访问权限（PRD §6.3.3）")
    return role


@dataclass
class AuthService:
    """认证用例（SRP）：OAuth 换档案 → 部门映角色 → 签发 JWT。依赖端口（DIP）。"""

    oauth: OAuthClient
    tokens: TokenService

    async def login(self, code: str) -> tuple[str, AuthUser]:
        profile = await self.oauth.exchange(code)
        role = role_for_dept(profile.dept)
        user = AuthUser(
            user_id=profile.user_id, name=profile.name, role=role, dept=profile.dept
        )
        return self.tokens.issue(user), user
