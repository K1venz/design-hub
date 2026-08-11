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
from design_hub.ports.password_reset import (
    PasswordResetAccountUnavailable,
    PasswordResetAttemptsExceeded,
    PasswordResetClaimContended,
    PasswordResetClaimed,
    PasswordResetCompleted,
    PasswordResetCooldown,
    PasswordResetStore,
)
from design_hub.ports.registration import (
    RegistrationAlreadyRegistered,
    RegistrationChallenge,
    RegistrationClaimContended,
    RegistrationClaimed,
    RegistrationClaimInvalid,
    RegistrationCompleted,
    RegistrationCooldown,
    RegistrationDuplicate,
    RegistrationStore,
)
from design_hub.ports.user_repository import UserAccount, UserRepository

_MIN_PASSWORD = 8
_CODE_DIGITS = 6
_GENERIC_FORGOT_MSG = "若该邮箱已注册，验证码将发送至邮箱（请查收，含垃圾箱）"
_INVALID_CODE_MSG = "验证码错误或已过期"


def _new_code() -> str:
    return f"{secrets.randbelow(10**_CODE_DIGITS):0{_CODE_DIGITS}d}"


class RegistrationDeliveryFailure(RuntimeError):
    def __init__(self, *, delivery_error: Exception, invalidation_error: Exception) -> None:
        self.delivery_error = delivery_error
        self.invalidation_error = invalidation_error
        super().__init__(
            "registration email delivery failed and challenge invalidation failed: "
            f"{delivery_error}; {invalidation_error}"
        )


class RegistrationActivationFailure(RuntimeError):
    def __init__(self, *, activation_error: Exception, invalidation_error: Exception) -> None:
        self.activation_error = activation_error
        self.invalidation_error = invalidation_error
        super().__init__(
            "registration challenge activation failed and invalidation failed: "
            f"{activation_error}; {invalidation_error}"
        )


class PasswordResetDeliveryFailure(RuntimeError):
    def __init__(self, *, delivery_error: Exception, invalidation_error: Exception) -> None:
        self.delivery_error = delivery_error
        self.invalidation_error = invalidation_error
        super().__init__(
            "password-reset email delivery failed and challenge invalidation failed: "
            f"{delivery_error}; {invalidation_error}"
        )


class PasswordResetActivationFailure(RuntimeError):
    def __init__(self, *, activation_error: Exception, invalidation_error: Exception) -> None:
        self.activation_error = activation_error
        self.invalidation_error = invalidation_error
        super().__init__(
            "password-reset challenge activation failed and invalidation failed: "
            f"{activation_error}; {invalidation_error}"
        )


def _to_auth_user(acc: UserAccount) -> AuthUser:
    # 自建认证无部门概念，dept 恒空（保留字段以兼容 JWT 载荷/MeResponse）
    return AuthUser(user_id=str(acc.id), name=acc.name, role=acc.role, dept=None)


@dataclass
class AccountService:
    users: UserRepository
    passwords: PasswordHasher
    tokens: TokenService
    resets: PasswordResetStore | None = None
    registrations: RegistrationStore | None = None
    mailer: MailPort | None = None
    email_verification_code_pepper: str = ""
    registration_code_ttl_seconds: int = 600
    registration_resend_cooldown_seconds: int = 60
    registration_max_attempts: int = 5
    reset_code_ttl_seconds: int = 600
    reset_resend_cooldown_seconds: int = 60
    reset_max_attempts: int = 5

    async def request_registration(self, *, email: str, password: str, name: str) -> str:
        self._require_registration_deps()
        assert self.registrations is not None
        email = email.strip().lower()
        if len(password) < _MIN_PASSWORD:
            raise ValueError(f"密码至少 {_MIN_PASSWORD} 位")
        if not name.strip():
            raise ValueError("姓名不能为空")
        now = datetime.now(UTC)
        code = _new_code()
        claim = await self.registrations.claim_initial(
            email=email,
            name=name.strip(),
            password_hash=self.passwords.hash(password),
            code_hash=self._registration_code_hash(email=email, code=code),
            expires_at=now + timedelta(seconds=self.registration_code_ttl_seconds),
            claimed_at=now,
            cooldown_seconds=self.registration_resend_cooldown_seconds,
        )
        challenge = self._require_claimed(claim, email=email)
        return await self._deliver_and_activate(challenge=challenge, code=code)

    async def resend_registration(self, *, email: str, challenge_id: str) -> str:
        self._require_registration_deps()
        assert self.registrations is not None
        email = email.strip().lower()
        now = datetime.now(UTC)
        code = _new_code()
        claim = await self.registrations.claim_resend(
            email=email,
            challenge_id=challenge_id.strip(),
            code_hash=self._registration_code_hash(email=email, code=code),
            expires_at=now + timedelta(seconds=self.registration_code_ttl_seconds),
            claimed_at=now,
            cooldown_seconds=self.registration_resend_cooldown_seconds,
        )
        challenge = self._require_claimed(claim, email=email)
        return await self._deliver_and_activate(challenge=challenge, code=code)

    async def verify_registration(
        self,
        *,
        email: str,
        challenge_id: str,
        code: str,
    ) -> tuple[str, AuthUser]:
        self._require_registration_deps()
        assert self.registrations is not None
        email = email.strip().lower()
        code = code.strip()
        if not code.isascii() or not code.isdigit() or len(code) != _CODE_DIGITS:
            raise ValueError(_INVALID_CODE_MSG)
        challenge = await self.registrations.get_active(
            email=email,
            challenge_id=challenge_id.strip(),
        )
        if challenge is None:
            raise ValueError(_INVALID_CODE_MSG)
        now = datetime.now(UTC)
        if _as_utc(challenge.expires_at) <= now:
            raise ValueError(_INVALID_CODE_MSG)
        if challenge.attempt_count >= self.registration_max_attempts:
            raise ValueError(_INVALID_CODE_MSG)
        actual = digest_verification_code(
            purpose="registration",
            email=email,
            code=code,
            pepper=self.email_verification_code_pepper,
        )
        if not hmac.compare_digest(challenge.code_hash, actual):
            await self.registrations.record_failed_attempt(
                challenge_id=challenge.id,
                delivery_id=challenge.delivery_id,
            )
            raise ValueError(_INVALID_CODE_MSG)
        completion = await self.registrations.complete(expected=challenge, completed_at=now)
        if isinstance(completion, RegistrationCompleted):
            user = _to_auth_user(completion.account)
            return self.tokens.issue(user), user
        if isinstance(completion, RegistrationDuplicate):
            raise DomainError(f"邮箱已注册：{email}")
        raise ValueError(_INVALID_CODE_MSG)

    async def login(self, *, email: str, password: str) -> tuple[str, AuthUser]:
        email = email.strip().lower()
        acc = await self.users.get_by_email(email)
        # 统一文案，不区分"邮箱不存在/密码错"，避免泄露账号存在性
        if acc is None or not acc.enabled or not self.passwords.verify(password, acc.password_hash):
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
        code = _new_code()
        claim = await self.resets.claim(
            email=email,
            code_hash=digest_verification_code(
                purpose="password-reset",
                email=email,
                code=code,
                pepper=self.email_verification_code_pepper,
            ),
            expires_at=now + timedelta(seconds=self.reset_code_ttl_seconds),
            claimed_at=now,
            cooldown_seconds=self.reset_resend_cooldown_seconds,
        )
        if isinstance(claim, PasswordResetAccountUnavailable):
            return _GENERIC_FORGOT_MSG
        if isinstance(claim, PasswordResetCooldown | PasswordResetClaimContended):
            raise ValueError(f"发送太频繁，请 {claim.retry_after_seconds} 秒后再试")
        if not isinstance(claim, PasswordResetClaimed):
            raise TypeError(f"unsupported password-reset claim outcome: {type(claim).__name__}")

        challenge = claim.challenge
        ttl_min = max(1, self.reset_code_ttl_seconds // 60)
        try:
            await self.mailer.send(
                to=email,
                subject="实朴 · 重置密码验证码",
                body_text=(
                    "您正在重置实朴账号密码。\n\n"
                    f"验证码：{code}\n"
                    f"有效期 {ttl_min} 分钟。请勿泄露给他人。\n\n"
                    "如非本人操作，请忽略本邮件。"
                ),
            )
        except Exception as delivery_error:
            try:
                invalidated = await self.resets.invalidate(
                    challenge_id=challenge.id,
                    delivery_id=challenge.delivery_id,
                    invalidated_at=datetime.now(UTC),
                )
                if not invalidated:
                    raise RuntimeError("expected password-reset delivery could not be invalidated")
            except Exception as invalidation_error:
                raise PasswordResetDeliveryFailure(
                    delivery_error=delivery_error,
                    invalidation_error=invalidation_error,
                ) from invalidation_error
            raise

        try:
            active = await self.resets.activate(
                challenge_id=challenge.id,
                delivery_id=challenge.delivery_id,
                activated_at=datetime.now(UTC),
            )
            if active is None:
                raise RuntimeError("password-reset challenge activation was rejected")
        except Exception as activation_error:
            try:
                invalidated = await self.resets.invalidate(
                    challenge_id=challenge.id,
                    delivery_id=challenge.delivery_id,
                    invalidated_at=datetime.now(UTC),
                )
                if not invalidated:
                    raise RuntimeError("expected password-reset delivery could not be invalidated")
            except Exception as invalidation_error:
                raise PasswordResetActivationFailure(
                    activation_error=activation_error,
                    invalidation_error=invalidation_error,
                ) from invalidation_error
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

        now = datetime.now(UTC)
        completion = await self.resets.complete(
            email=email,
            code_hash=digest_verification_code(
                purpose="password-reset",
                email=email,
                code=code,
                pepper=self.email_verification_code_pepper,
            ),
            password_hash=self.passwords.hash(password),
            completed_at=now,
            max_attempts=self.reset_max_attempts,
        )
        if isinstance(completion, PasswordResetCompleted):
            return
        if isinstance(completion, PasswordResetAttemptsExceeded):
            raise ValueError("验证码错误次数过多，请重新获取")
        raise ValueError(_INVALID_CODE_MSG)

    def _require_reset_deps(self) -> None:
        if self.resets is None or self.mailer is None or not self.email_verification_code_pepper:
            raise RuntimeError("password reset is not configured")

    def _registration_code_hash(self, *, email: str, code: str) -> str:
        return digest_verification_code(
            purpose="registration",
            email=email,
            code=code,
            pepper=self.email_verification_code_pepper,
        )

    def _require_claimed(
        self,
        claim: object,
        *,
        email: str,
    ) -> RegistrationChallenge:
        if isinstance(claim, RegistrationClaimed):
            return claim.challenge
        if isinstance(claim, RegistrationAlreadyRegistered):
            raise DomainError(f"邮箱已注册：{email}")
        if isinstance(claim, RegistrationCooldown | RegistrationClaimContended):
            raise ValueError(f"发送过于频繁，请 {claim.retry_after_seconds} 秒后再试")
        if isinstance(claim, RegistrationClaimInvalid):
            raise ValueError(_INVALID_CODE_MSG)
        raise TypeError(f"unsupported registration claim outcome: {type(claim).__name__}")

    async def _deliver_and_activate(
        self,
        *,
        challenge: RegistrationChallenge,
        code: str,
    ) -> str:
        assert self.registrations is not None
        try:
            await self._send_registration_code(email=challenge.email, code=code)
        except Exception as delivery_error:
            try:
                invalidated = await self.registrations.invalidate(
                    challenge_id=challenge.id,
                    delivery_id=challenge.delivery_id,
                    invalidated_at=datetime.now(UTC),
                )
                if not invalidated:
                    raise RuntimeError("expected registration delivery could not be invalidated")
            except Exception as invalidation_error:
                raise RegistrationDeliveryFailure(
                    delivery_error=delivery_error,
                    invalidation_error=invalidation_error,
                ) from invalidation_error
            raise

        try:
            active = await self.registrations.activate(
                challenge_id=challenge.id,
                delivery_id=challenge.delivery_id,
                activated_at=datetime.now(UTC),
            )
            if active is None:
                raise RuntimeError("registration challenge activation was rejected")
        except Exception as activation_error:
            try:
                invalidated = await self.registrations.invalidate(
                    challenge_id=challenge.id,
                    delivery_id=challenge.delivery_id,
                    invalidated_at=datetime.now(UTC),
                )
                if not invalidated:
                    raise RuntimeError("expected registration delivery could not be invalidated")
            except Exception as invalidation_error:
                raise RegistrationActivationFailure(
                    activation_error=activation_error,
                    invalidation_error=invalidation_error,
                ) from invalidation_error
            raise
        return active.id

    async def _send_registration_code(self, *, email: str, code: str) -> None:
        assert self.mailer is not None
        ttl_min = max(1, self.registration_code_ttl_seconds // 60)
        await self.mailer.send(
            to=email,
            subject="实朴 · 注册验证码",
            body_text=(
                "您正在注册实朴账号。\n\n"
                f"验证码：{code}\n"
                f"有效期：{ttl_min} 分钟。请勿泄露给他人。\n\n"
                "如非本人操作，请忽略本邮件。"
            ),
        )

    def _require_registration_deps(self) -> None:
        if (
            self.registrations is None
            or self.mailer is None
            or not self.email_verification_code_pepper
        ):
            raise RuntimeError("registration verification is not configured")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
