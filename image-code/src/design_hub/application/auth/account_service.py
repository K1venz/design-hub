"""自建邮箱密码认证用例（ISSUE-0015，替换 OAuth）。

复用 JWT 签发(TokenService) + Role 枚举；只替换"如何获得身份"。fail-fast：
注册重复→DomainError(409)、弱密码→ValueError(400)、登录失败→AuthenticationError(401)。
"""

from __future__ import annotations

import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from design_hub.application.auth.verification_codes import digest_verification_code
from design_hub.domain.enums import Role
from design_hub.domain.errors import AuthenticationError, DomainError
from design_hub.domain.models import AuthUser
from design_hub.ports.auth import TokenService
from design_hub.ports.mail import MailPort
from design_hub.ports.password import PasswordHasher
from design_hub.ports.password_reset import PasswordResetStore
from design_hub.ports.user_repository import UserAccount, UserRepository

_MIN_PASSWORD = 8
_CODE_DIGITS = 6
_GENERIC_FORGOT_MSG = "若该邮箱已注册，验证码将发送至邮箱（请查收，含垃圾箱）"
_INVALID_CODE_MSG = "验证码错误或已过期"


def _to_auth_user(acc: UserAccount) -> AuthUser:
    # 自建认证无部门概念，dept 恒空（保留字段以兼容 JWT 载荷/MeResponse）
    return AuthUser(user_id=str(acc.id), name=acc.name, role=acc.role, dept=None)


@dataclass
class AccountService:
    users: UserRepository
    passwords: PasswordHasher
    tokens: TokenService
    resets: PasswordResetStore | None = None
    mailer: MailPort | None = None
    email_verification_code_pepper: str = ""
    reset_code_ttl_seconds: int = 600
    reset_resend_cooldown_seconds: int = 60
    reset_max_attempts: int = 5

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
        if (
            acc is None
            or not acc.enabled
            or not self.passwords.verify(password, acc.password_hash)
        ):
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

    async def request_password_reset(self, *, email: str) -> str:
        """Send a one-time code if the account exists. Always returns the same copy."""
        self._require_reset_deps()
        assert self.resets is not None and self.mailer is not None
        email = email.strip().lower()
        now = datetime.now(UTC)
        active = await self.resets.get_active(email)
        if active is not None:
            created = active.created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=UTC)
            age = (now - created).total_seconds()
            if age < self.reset_resend_cooldown_seconds:
                wait = int(self.reset_resend_cooldown_seconds - age) + 1
                raise ValueError(f"发送太频繁，请 {wait} 秒后再试")

        acc = await self.users.get_by_email(email)
        if acc is not None and acc.enabled:
            code = f"{secrets.randbelow(10**_CODE_DIGITS):0{_CODE_DIGITS}d}"
            code_hash = digest_verification_code(
                purpose="password-reset",
                email=email,
                code=code,
                pepper=self.email_verification_code_pepper,
            )
            expires_at = now + timedelta(seconds=self.reset_code_ttl_seconds)
            challenge = await self.resets.replace_active(
                email=email, code_hash=code_hash, expires_at=expires_at
            )
            ttl_min = max(1, self.reset_code_ttl_seconds // 60)
            try:
                await self.mailer.send(
                    to=email,
                    subject="实朴 · 重置密码验证码",
                    body_text=(
                        f"您正在重置实朴账号密码。\n\n"
                        f"验证码：{code}\n"
                        f"有效期 {ttl_min} 分钟。请勿泄露给他人。\n\n"
                        f"如非本人操作，请忽略本邮件。"
                    ),
                )
            except Exception:
                await self.resets.consume(challenge.id)
                raise
        return _GENERIC_FORGOT_MSG

    async def reset_password(self, *, email: str, code: str, password: str) -> None:
        """Verify code and set a new password. Invalid code/email → same 400 copy."""
        self._require_reset_deps()
        assert self.resets is not None
        email = email.strip().lower()
        code = code.strip()
        if len(password) < _MIN_PASSWORD:
            raise ValueError(f"密码至少 {_MIN_PASSWORD} 位")
        if not code.isdigit() or len(code) != _CODE_DIGITS:
            raise ValueError(_INVALID_CODE_MSG)

        challenge = await self.resets.get_active(email)
        if challenge is None:
            raise ValueError(_INVALID_CODE_MSG)
        now = datetime.now(UTC)
        expires = challenge.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        if now > expires:
            raise ValueError(_INVALID_CODE_MSG)
        if challenge.attempt_count >= self.reset_max_attempts:
            raise ValueError("验证码错误次数过多，请重新获取")

        expected = challenge.code_hash
        actual = digest_verification_code(
            purpose="password-reset",
            email=email,
            code=code,
            pepper=self.email_verification_code_pepper,
        )
        if not hmac.compare_digest(expected, actual):
            updated = await self.resets.record_failed_attempt(challenge.id)
            if updated is not None and updated.attempt_count >= self.reset_max_attempts:
                raise ValueError("验证码错误次数过多，请重新获取")
            raise ValueError(_INVALID_CODE_MSG)

        acc = await self.users.get_by_email(email)
        if acc is None or not acc.enabled:
            raise ValueError(_INVALID_CODE_MSG)

        await self.users.update_password_hash(
            user_id=acc.id, password_hash=self.passwords.hash(password)
        )
        await self.resets.consume(challenge.id)

    def _require_reset_deps(self) -> None:
        if (
            self.resets is None
            or self.mailer is None
            or not self.email_verification_code_pepper
        ):
            raise RuntimeError("password reset is not configured")
