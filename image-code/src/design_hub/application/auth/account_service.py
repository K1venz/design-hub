"""自建邮箱密码认证用例（ISSUE-0015，替换 OAuth）。

复用 JWT 签发(TokenService) + Role 枚举；只替换"如何获得身份"。fail-fast：
注册重复→DomainError(409)、弱密码→ValueError(400)、登录失败→AuthenticationError(401)。
"""

from dataclasses import dataclass

from design_hub.domain.enums import Role
from design_hub.domain.errors import AuthenticationError, DomainError
from design_hub.domain.models import AuthUser
from design_hub.ports.auth import TokenService
from design_hub.ports.password import PasswordHasher
from design_hub.ports.user_repository import UserAccount, UserRepository

_MIN_PASSWORD = 8


def _to_auth_user(acc: UserAccount) -> AuthUser:
    # 自建认证无部门概念，dept 恒空（保留字段以兼容 JWT 载荷/MeResponse）
    return AuthUser(user_id=str(acc.id), name=acc.name, role=acc.role, dept=None)


@dataclass
class AccountService:
    users: UserRepository
    passwords: PasswordHasher
    tokens: TokenService

    async def register(self, *, email: str, password: str, name: str) -> tuple[str, AuthUser]:
        email = email.strip().lower()
        if len(password) < _MIN_PASSWORD:
            raise ValueError(f"密码至少 {_MIN_PASSWORD} 位")
        if not name.strip():
            raise ValueError("姓名不能为空")
        if await self.users.get_by_email(email) is not None:
            raise DomainError(f"邮箱已注册：{email}")  # 409
        acc = await self.users.add(
            email=email,
            password_hash=self.passwords.hash(password),
            name=name.strip(),
            role=Role.DESIGNER,  # 注册默认设计师；管理者由后台提升
        )
        user = _to_auth_user(acc)
        return self.tokens.issue(user), user

    async def login(self, *, email: str, password: str) -> tuple[str, AuthUser]:
        email = email.strip().lower()
        acc = await self.users.get_by_email(email)
        # 统一文案，不区分"邮箱不存在/密码错"，避免泄露账号存在性
        if acc is None or not self.passwords.verify(password, acc.password_hash):
            raise AuthenticationError("邮箱或密码错误")  # 401
        user = _to_auth_user(acc)
        return self.tokens.issue(user), user

    async def seed_admin(self, *, email: str, password: str, name: str = "管理员") -> None:
        """启动幂等 seed 首个管理者（邮箱/密码走 .env）。已存在则跳过。"""
        email = email.strip().lower()
        if await self.users.get_by_email(email) is not None:
            return
        await self.users.add(
            email=email,
            password_hash=self.passwords.hash(password),
            name=name,
            role=Role.MANAGER,
        )
