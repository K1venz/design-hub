"""登录健壮性（ISSUE-0058）：滑动续期 + 密码传输公钥加密。

单元：jwt renew_if_stale（半衰期前/后/过期）。
集成（TestClient + 假 repo + 真 cipher/token）：/auth/pubkey、密文注册登录往返、
解密失败 400、明文<8 → 400、/me 过半衰期回 X-Renewed-Token、fresh 无头、过期 401。
"""

import asyncio
import re
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient

from design_hub.application.auth.account_service import (
    AccountService,
    RegistrationActivationFailure,
    RegistrationDeliveryFailure,
)
from design_hub.application.auth.verification_codes import digest_verification_code
from design_hub.domain.enums import Role
from design_hub.domain.errors import AuthenticationError, DomainError, NotFoundError
from design_hub.domain.models import AuthUser
from design_hub.infrastructure.auth.jwt_service import PyJwtTokenService
from design_hub.infrastructure.auth.password import BcryptPasswordHasher
from design_hub.infrastructure.security.rsa_secret_cipher import RsaSecretCipher
from design_hub.interface.api.app import register_error_handlers
from design_hub.interface.api.deps import CurrentUserSseDep
from design_hub.interface.api.routes import auth
from design_hub.ports.auth import TokenService
from design_hub.ports.mail import MailPort
from design_hub.ports.password_reset import (
    PasswordResetAccountUnavailable,
    PasswordResetAttemptsExceeded,
    PasswordResetChallenge,
    PasswordResetClaim,
    PasswordResetClaimed,
    PasswordResetCompleted,
    PasswordResetCompletion,
    PasswordResetCooldown,
    PasswordResetDeliveryState,
    PasswordResetInvalid,
    PasswordResetStore,
)
from design_hub.ports.registration import (
    InitialRegistrationClaim,
    RegistrationAlreadyRegistered,
    RegistrationChallenge,
    RegistrationClaimed,
    RegistrationClaimInvalid,
    RegistrationCompleted,
    RegistrationCompletion,
    RegistrationCooldown,
    RegistrationDeliveryState,
    RegistrationDuplicate,
    RegistrationInvalid,
    RegistrationStore,
    ResendRegistrationClaim,
)
from design_hub.ports.user_repository import UserAccount, UserRepository

_SECRET = "test-secret-min-32-bytes-aaaaaaaaaaaa"


def _backdated_token(iat_hours_ago: float, ttl_hours: int = 24) -> str:
    iat = datetime.now(UTC) - timedelta(hours=iat_hours_ago)
    payload = {
        "sub": "7",
        "name": "t",
        "role": Role.DESIGNER.value,
        "dept": None,
        "iat": iat,
        "exp": iat + timedelta(hours=ttl_hours),
    }
    return jwt.encode(payload, _SECRET, algorithm="HS256")


# ── 单元：滑动续期 ──────────────────────────────────────────────────────────


def test_renew_if_stale_fresh_returns_none() -> None:
    svc = PyJwtTokenService(secret=_SECRET, renew_after_hours=12)
    token = _backdated_token(1)
    assert svc.renew_if_stale(token, svc.verify(token)) is None  # 1h < 12h 半衰期


def test_renew_if_stale_past_halflife_issues_new_valid_token() -> None:
    svc = PyJwtTokenService(secret=_SECRET, renew_after_hours=12)
    tok = _backdated_token(13)  # 13h 老、仍未过期(exp=iat+24=now+11h)
    current = svc.verify(tok)
    new = svc.renew_if_stale(tok, current)
    assert new is not None and new != tok  # iat 差 13h → 新令牌不同
    assert svc.verify(new).user_id == "7"
    assert svc.renew_if_stale(new, svc.verify(new)) is None  # 新令牌 fresh、不再续


def test_verify_expired_raises() -> None:
    svc = PyJwtTokenService(secret=_SECRET, renew_after_hours=12)
    with pytest.raises(AuthenticationError):
        svc.verify(_backdated_token(30))  # exp=iat+24=now-6h 已过期


# ── 集成：/auth 路由（假 repo + 真 cipher/token via TestClient）─────────────


class _FakeUserRepo(UserRepository):
    def __init__(self) -> None:
        self._by_email: dict[str, UserAccount] = {}
        self._seq = 0

    async def get_by_email(self, email: str) -> UserAccount | None:
        return self._by_email.get(email)

    async def get_by_id(self, user_id: int) -> UserAccount | None:
        return next((a for a in self._by_email.values() if a.id == user_id), None)

    async def add(self, *, email: str, password_hash: str, name: str, role: Role) -> UserAccount:
        self._seq += 1
        acc = UserAccount(
            id=self._seq,
            email=email,
            name=name,
            role=role,
            created_at=datetime.now(UTC),
            password_hash=password_hash,
        )
        self._by_email[email] = acc
        return acc

    async def set_role_with_audit(
        self,
        *,
        actor_id: int,
        user_id: int,
        role: Role,
    ) -> UserAccount:
        del actor_id, user_id, role
        raise NotImplementedError

    async def set_status_with_audit(
        self,
        *,
        actor_id: int,
        user_id: int,
        enabled: bool,
        reason: str,
    ) -> UserAccount:
        del actor_id, user_id, enabled, reason
        raise NotImplementedError

    async def list_all(self) -> list[UserAccount]:
        return list(self._by_email.values())

    async def update_password_hash(self, *, user_id: int, password_hash: str) -> None:
        for email, acc in list(self._by_email.items()):
            if acc.id == user_id:
                self._by_email[email] = UserAccount(
                    id=acc.id,
                    email=acc.email,
                    name=acc.name,
                    role=acc.role,
                    created_at=acc.created_at,
                    password_hash=password_hash,
                    enabled=acc.enabled,
                    disabled_at=acc.disabled_at,
                    disabled_by=acc.disabled_by,
                    disabled_reason=acc.disabled_reason,
                )
                return
        raise NotFoundError(f"user {user_id} not found")


class _FakeMailer(MailPort):
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    async def send(self, *, to: str, subject: str, body_text: str) -> None:
        self.sent.append((to, subject, body_text))


class _FailingMailer(MailPort):
    async def send(self, *, to: str, subject: str, body_text: str) -> None:
        raise OSError("smtp unavailable")


class _FakeResetStore(PasswordResetStore):
    def __init__(self, users: _FakeUserRepo) -> None:
        self._users = users
        self._items: dict[str, PasswordResetChallenge] = {}
        self._seq = 0
        self.activation_returns_none = False

    async def claim(
        self,
        *,
        email: str,
        code_hash: str,
        expires_at: datetime,
        claimed_at: datetime,
        cooldown_seconds: int,
    ) -> PasswordResetClaim:
        account = self._users._by_email.get(email)
        if account is None or not account.enabled:
            return PasswordResetAccountUnavailable()
        previous = self._items.get(email)
        if (
            previous is not None
            and previous.delivery_state
            in (PasswordResetDeliveryState.PENDING, PasswordResetDeliveryState.ACTIVE)
            and (claimed_at - previous.delivery_claimed_at).total_seconds() < cooldown_seconds
        ):
            return PasswordResetCooldown(cooldown_seconds)
        self._seq += 1
        challenge = PasswordResetChallenge(
            id=f"reset-{self._seq}",
            delivery_id=f"delivery-{self._seq}",
            email=email,
            code_hash=code_hash,
            delivery_state=PasswordResetDeliveryState.PENDING,
            expires_at=expires_at,
            attempt_count=0,
            created_at=claimed_at,
            delivery_claimed_at=claimed_at,
            activated_at=None,
            consumed_at=None,
        )
        self._items[email] = challenge
        return PasswordResetClaimed(challenge)

    async def activate(
        self,
        *,
        challenge_id: str,
        delivery_id: str,
        activated_at: datetime,
    ) -> PasswordResetChallenge | None:
        if self.activation_returns_none:
            return None
        for email, challenge in self._items.items():
            if (
                challenge.id == challenge_id
                and challenge.delivery_id == delivery_id
                and challenge.delivery_state is PasswordResetDeliveryState.PENDING
            ):
                active = replace(
                    challenge,
                    delivery_state=PasswordResetDeliveryState.ACTIVE,
                    activated_at=activated_at,
                )
                self._items[email] = active
                return active
        return None

    async def get_active(self, *, email: str) -> PasswordResetChallenge | None:
        challenge = self._items.get(email)
        if (
            challenge is None
            or challenge.delivery_state is not PasswordResetDeliveryState.ACTIVE
            or challenge.consumed_at is not None
        ):
            return None
        return challenge

    async def invalidate(
        self,
        *,
        challenge_id: str,
        delivery_id: str,
        invalidated_at: datetime,
    ) -> bool:
        for email, challenge in self._items.items():
            if challenge.id == challenge_id and challenge.delivery_id == delivery_id:
                self._items[email] = replace(
                    challenge,
                    delivery_state=PasswordResetDeliveryState.CONSUMED,
                    consumed_at=invalidated_at,
                )
                return True
        return False

    async def complete(
        self,
        *,
        email: str,
        code_hash: str,
        password_hash_factory: Callable[[], str],
        completed_at: datetime,
        max_attempts: int,
    ) -> PasswordResetCompletion:
        challenge = self._items.get(email)
        if (
            challenge is None
            or challenge.delivery_state is not PasswordResetDeliveryState.ACTIVE
            or challenge.expires_at <= completed_at
            or challenge.consumed_at is not None
        ):
            return PasswordResetInvalid()
        if challenge.attempt_count >= max_attempts:
            return PasswordResetAttemptsExceeded()
        if challenge.code_hash != code_hash:
            updated = replace(challenge, attempt_count=challenge.attempt_count + 1)
            self._items[email] = updated
            if updated.attempt_count >= max_attempts:
                return PasswordResetAttemptsExceeded()
            return PasswordResetInvalid()
        account = self._users._by_email.get(email)
        if account is None or not account.enabled:
            return PasswordResetInvalid()
        self._users._by_email[email] = replace(
            account,
            password_hash=password_hash_factory(),
        )
        self._items[email] = replace(
            challenge,
            delivery_state=PasswordResetDeliveryState.CONSUMED,
            consumed_at=completed_at,
        )
        return PasswordResetCompleted()


def _client(
    mailer: MailPort | None = None,
) -> tuple[
    TestClient,
    RsaSecretCipher,
    PyJwtTokenService,
    _FakeUserRepo,
    MailPort,
    _FakeResetStore,
]:
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(auth.router)

    @app.get("/test/sse-auth")
    async def sse_auth(user: CurrentUserSseDep) -> dict[str, str]:
        return {"user_id": user.user_id}

    token_service = PyJwtTokenService(secret=_SECRET, renew_after_hours=12)
    cipher = RsaSecretCipher.generate()
    app.state.token_service = token_service
    app.state.secret_cipher = cipher
    users = _FakeUserRepo()
    users._seq = 7
    users._by_email["token-user@example.com"] = UserAccount(
        id=7,
        email="token-user@example.com",
        name="t",
        role=Role.DESIGNER,
        created_at=datetime.now(UTC),
        password_hash="hash",
    )
    app.state.user_repository = users
    mailer = mailer or _FakeMailer()
    resets = _FakeResetStore(users)
    app.state.account_service = AccountService(
        users=users,
        passwords=BcryptPasswordHasher(),
        tokens=token_service,
        resets=resets,
        registrations=_FakeRegistrationStore(users),
        mailer=mailer,
        email_verification_code_pepper=_SECRET,
        registration_code_ttl_seconds=600,
        registration_resend_cooldown_seconds=60,
        registration_max_attempts=5,
        reset_code_ttl_seconds=600,
        reset_resend_cooldown_seconds=60,
        reset_max_attempts=5,
    )
    return TestClient(app), cipher, token_service, users, mailer, resets


def test_pubkey_returns_spki_pem() -> None:
    client, _, _, _, _, _ = _client()
    resp = client.get("/auth/pubkey")
    assert resp.status_code == 200
    pem = resp.json()["public_key"]
    assert pem.startswith("-----BEGIN PUBLIC KEY-----")
    assert isinstance(serialization.load_pem_public_key(pem.encode()), rsa.RSAPublicKey)


def test_login_existing_account_round_trip_encrypted_password() -> None:
    client, cipher, _, users, _, _ = _client()
    asyncio.run(
        users.add(
            email="a@b.com",
            password_hash=BcryptPasswordHasher().hash("mypassword8"),
            name="A",
            role=Role.DESIGNER,
        )
    )
    login = client.post(
        "/auth/login",
        json={"email": "a@b.com", "password": cipher.encrypt("mypassword8")},
    )
    assert login.status_code == 200 and login.json()["jwt"]


def test_login_garbage_ciphertext_uses_password_specific_error() -> None:
    client, _, _, _, _, _ = _client()
    resp = client.post("/auth/login", json={"email": "a@b.com", "password": "garbage-not-cipher"})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "密码解密失败，请刷新页面后重试"


def test_registration_http_flow_requires_verification_before_login() -> None:
    client, cipher, _, _, mailer, _ = _client()

    requested = client.post(
        "/auth/register",
        json={
            "email": "new@example.com",
            "password": cipher.encrypt("password88"),
            "name": "New User",
        },
    )

    assert requested.status_code == 200
    assert set(requested.json()) == {"message", "challenge_id"}
    challenge_id = requested.json()["challenge_id"]
    assert "jwt" not in requested.json()

    pending_login = client.post(
        "/auth/login",
        json={"email": "new@example.com", "password": cipher.encrypt("password88")},
    )
    assert pending_login.status_code == 401

    verified = client.post(
        "/auth/register/verify",
        json={
            "email": "new@example.com",
            "challenge_id": challenge_id,
            "code": _code_from_mail(mailer),
        },
    )
    assert verified.status_code == 200
    assert set(verified.json()) == {"jwt", "role", "name"}
    assert verified.json()["name"] == "New User"


def test_registration_resend_returns_acknowledgement() -> None:
    client, cipher, _, _, mailer, _ = _client()
    requested = client.post(
        "/auth/register",
        json={
            "email": "resend@example.com",
            "password": cipher.encrypt("password88"),
            "name": "Resend User",
        },
    )
    assert requested.status_code == 200
    challenge_id = requested.json()["challenge_id"]
    service = client.app.state.account_service
    registration = service.registrations.current("resend@example.com")
    assert registration is not None
    service.registrations.set_current(
        replace(
            registration,
            delivery_claimed_at=datetime.now(UTC) - timedelta(seconds=61),
        )
    )

    resent = client.post(
        "/auth/register/resend",
        json={"email": "resend@example.com", "challenge_id": challenge_id},
    )

    assert resent.status_code == 200
    assert resent.json()["challenge_id"] != challenge_id
    assert len(mailer.sent) == 2


def test_registration_http_validation_and_status_mapping() -> None:
    client, cipher, _, users, _, _ = _client()
    asyncio.run(
        users.add(
            email="registered@example.com",
            password_hash=BcryptPasswordHasher().hash("password88"),
            name="Registered",
            role=Role.DESIGNER,
        )
    )

    duplicate = client.post(
        "/auth/register",
        json={
            "email": "registered@example.com",
            "password": cipher.encrypt("password88"),
            "name": "Duplicate",
        },
    )
    malformed = client.post(
        "/auth/register/verify",
        json={
            "email": "not-an-email",
            "challenge_id": "challenge-does-not-exist-1234567890",
            "code": "12345",
        },
    )
    forbidden_fields = client.post(
        "/auth/register/resend",
        json={
            "email": "registered@example.com",
            "challenge_id": "challenge-does-not-exist-1234567890",
            "name": "Not Accepted",
        },
    )
    forbidden_verify_fields = client.post(
        "/auth/register/verify",
        json={
            "email": "registered@example.com",
            "challenge_id": "challenge-does-not-exist-1234567890",
            "code": "000000",
            "password": "Not Accepted",
        },
    )
    invalid_code = client.post(
        "/auth/register/verify",
        json={
            "email": "registered@example.com",
            "challenge_id": "challenge-does-not-exist-1234567890",
            "code": "000000",
        },
    )

    assert duplicate.status_code == 409
    assert malformed.status_code == 422
    assert forbidden_fields.status_code == 422
    assert forbidden_verify_fields.status_code == 422
    assert invalid_code.status_code == 400
    assert invalid_code.json()["detail"] == "验证码错误或已过期"


@pytest.mark.parametrize("code", ["１２３４５６", "١٢٣٤٥٦"])
def test_registration_verification_rejects_non_ascii_digits_at_http_boundary(
    code: str,
) -> None:
    client, _, _, _, _, _ = _client()

    response = client.post(
        "/auth/register/verify",
        json={
            "email": "unicode-digits@example.com",
            "challenge_id": "challenge-does-not-exist-1234567890",
            "code": code,
        },
    )

    assert response.status_code == 422


def test_request_registration_rejects_short_password() -> None:
    async def run() -> None:
        service, _, _, _, _, _ = _registration_service()

        with pytest.raises(ValueError):
            await service.request_registration(
                email="short@example.com", password="short", name="Short"
            )

    asyncio.run(run())


def test_me_stale_token_returns_renewed_header() -> None:
    client, _, token_service, _, _, _ = _client()
    resp = client.get("/me", headers={"Authorization": f"Bearer {_backdated_token(13)}"})
    assert resp.status_code == 200
    assert "X-Renewed-Token" in resp.headers
    assert token_service.verify(resp.headers["X-Renewed-Token"]).user_id == "7"


def test_me_fresh_token_no_renewed_header() -> None:
    client, _, token_service, _, _, _ = _client()
    fresh = token_service.issue(AuthUser(user_id="7", name="t", role=Role.DESIGNER, dept=None))
    resp = client.get("/me", headers={"Authorization": f"Bearer {fresh}"})
    assert resp.status_code == 200 and "X-Renewed-Token" not in resp.headers


def test_me_expired_token_401_no_renewal() -> None:
    client, _, _, _, _, _ = _client()
    resp = client.get("/me", headers={"Authorization": f"Bearer {_backdated_token(30)}"})
    assert resp.status_code == 401 and "X-Renewed-Token" not in resp.headers


def test_me_uses_current_database_role_instead_of_token_snapshot() -> None:
    client, _, _, users, _, _ = _client()
    account = users._by_email["token-user@example.com"]
    object.__setattr__(account, "role", Role.MANAGER)

    response = client.get(
        "/me",
        headers={"Authorization": f"Bearer {_backdated_token(1)}"},
    )

    assert response.status_code == 200
    assert response.json()["role"] == Role.MANAGER.value


def test_disabled_token_is_rejected_on_next_request() -> None:
    client, _, token_service, users, _, _ = _client()
    account = users._by_email["token-user@example.com"]
    object.__setattr__(account, "enabled", False)
    token = token_service.issue(AuthUser(user_id="7", name="t", role=Role.DESIGNER, dept=None))

    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.json()["error"] == "unauthenticated"


def test_disabled_sse_token_is_rejected_on_next_request() -> None:
    client, _, token_service, users, _, _ = _client()
    account = users._by_email["token-user@example.com"]
    object.__setattr__(account, "enabled", False)
    token = token_service.issue(AuthUser(user_id="7", name="t", role=Role.DESIGNER, dept=None))

    response = client.get(f"/test/sse-auth?access_token={token}")

    assert response.status_code == 401
    assert response.json()["error"] == "unauthenticated"


def test_disabled_user_cannot_log_in_again() -> None:
    client, cipher, _, users, _, _ = _client()
    asyncio.run(
        users.add(
            email="disabled@example.com",
            password_hash=BcryptPasswordHasher().hash("mypassword8"),
            name="Disabled",
            role=Role.DESIGNER,
        )
    )
    account = users._by_email["disabled@example.com"]
    object.__setattr__(account, "enabled", False)

    response = client.post(
        "/auth/login",
        json={
            "email": "disabled@example.com",
            "password": cipher.encrypt("mypassword8"),
        },
    )

    assert response.status_code == 401
    assert response.json()["error"] == "unauthenticated"


def _code_from_mail(mailer: _FakeMailer) -> str:
    assert mailer.sent
    body = mailer.sent[-1][2]
    for line in body.splitlines():
        if line.startswith("验证码："):
            return line.removeprefix("验证码：").strip()
    raise AssertionError(f"no code in mail body: {body!r}")


def test_forgot_password_unknown_email_same_message_no_mail() -> None:
    client, _, _, _, mailer, _ = _client()
    resp = client.post("/auth/forgot-password", json={"email": "nobody@x.com"})
    assert resp.status_code == 200
    assert "验证码" in resp.json()["message"]
    assert mailer.sent == []


def test_password_reset_round_trip() -> None:
    client, cipher, _, users, mailer, resets = _client()
    asyncio.run(
        users.add(
            email="reset@example.com",
            password_hash=BcryptPasswordHasher().hash("oldpassword1"),
            name="R",
            role=Role.DESIGNER,
        )
    )

    forgot = client.post("/auth/forgot-password", json={"email": "reset@example.com"})
    assert forgot.status_code == 200
    code = _code_from_mail(mailer)
    challenge = asyncio.run(resets.get_active(email="reset@example.com"))
    assert challenge is not None
    assert challenge.code_hash == digest_verification_code(
        purpose="password-reset",
        email="reset@example.com",
        code=code,
        pepper=_SECRET,
    )

    reset = client.post(
        "/auth/reset-password",
        json={
            "email": "reset@example.com",
            "code": code,
            "password": cipher.encrypt("newpassword9"),
        },
    )
    assert reset.status_code == 200

    bad_old = client.post(
        "/auth/login",
        json={"email": "reset@example.com", "password": cipher.encrypt("oldpassword1")},
    )
    assert bad_old.status_code == 401

    ok_new = client.post(
        "/auth/login",
        json={"email": "reset@example.com", "password": cipher.encrypt("newpassword9")},
    )
    assert ok_new.status_code == 200 and ok_new.json()["jwt"]


def test_password_reset_wrong_code_400() -> None:
    client, cipher, _, users, mailer, _ = _client()
    asyncio.run(
        users.add(
            email="wrong@x.com",
            password_hash=BcryptPasswordHasher().hash("oldpassword1"),
            name="W",
            role=Role.DESIGNER,
        )
    )
    client.post("/auth/forgot-password", json={"email": "wrong@x.com"})
    assert mailer.sent
    resp = client.post(
        "/auth/reset-password",
        json={
            "email": "wrong@x.com",
            "code": "000000",
            "password": cipher.encrypt("newpassword9"),
        },
    )
    assert resp.status_code == 400
    assert "验证码" in resp.json()["detail"]


def test_forgot_password_cooldown() -> None:
    client, _, _, users, mailer, _ = _client()
    asyncio.run(
        users.add(
            email="cool@x.com",
            password_hash=BcryptPasswordHasher().hash("oldpassword1"),
            name="C",
            role=Role.DESIGNER,
        )
    )
    first = client.post("/auth/forgot-password", json={"email": "cool@x.com"})
    again = client.post("/auth/forgot-password", json={"email": "cool@x.com"})
    assert first.status_code == 200
    assert again.status_code == 200
    assert again.json() == first.json()
    assert isinstance(mailer, _FakeMailer)
    assert len(mailer.sent) == 1


def test_forgot_password_mail_failure_invalidates_challenge() -> None:
    async def run() -> None:
        _, _, _, users, _, resets = _client(mailer=_FailingMailer())
        users._by_email["mailfail@x.com"] = UserAccount(
            id=8,
            email="mailfail@x.com",
            name="M",
            role=Role.DESIGNER,
            created_at=datetime.now(UTC),
            password_hash="hash",
        )
        service = AccountService(
            users=users,
            passwords=BcryptPasswordHasher(),
            tokens=PyJwtTokenService(secret=_SECRET),
            resets=resets,
            mailer=_FailingMailer(),
            email_verification_code_pepper=_SECRET,
        )

        generic = await service.request_password_reset(email="unknown@x.com")
        first = await service.request_password_reset(email="mailfail@x.com")
        assert first == generic
        assert await resets.get_active(email="mailfail@x.com") is None

        second = await service.request_password_reset(email="mailfail@x.com")
        assert second == generic

    asyncio.run(run())


def test_invalid_password_reset_does_not_hash_the_new_password() -> None:
    async def run() -> None:
        _, _, _, users, mailer, resets = _client()
        users._by_email["cheap-invalid@x.com"] = UserAccount(
            id=8,
            email="cheap-invalid@x.com",
            name="C",
            role=Role.DESIGNER,
            created_at=datetime.now(UTC),
            password_hash="old-hash",
        )
        passwords = _CountingPasswordHasher()
        service = AccountService(
            users=users,
            passwords=passwords,
            tokens=PyJwtTokenService(secret=_SECRET),
            resets=resets,
            mailer=mailer,
            email_verification_code_pepper=_SECRET,
        )
        await service.request_password_reset(email="cheap-invalid@x.com")

        with pytest.raises(ValueError, match="验证码"):
            await service.reset_password(
                email="cheap-invalid@x.com",
                code="000000",
                password="newpassword9",
            )

        assert passwords.hash_calls == []

    asyncio.run(run())


def test_password_reset_activation_failure_is_publicly_indistinguishable() -> None:
    async def run() -> None:
        _, _, _, users, mailer, resets = _client()
        users._by_email["activation-fail@x.com"] = UserAccount(
            id=8,
            email="activation-fail@x.com",
            name="A",
            role=Role.DESIGNER,
            created_at=datetime.now(UTC),
            password_hash="old-hash",
        )
        resets.activation_returns_none = True
        service = AccountService(
            users=users,
            passwords=BcryptPasswordHasher(),
            tokens=PyJwtTokenService(secret=_SECRET),
            resets=resets,
            mailer=mailer,
            email_verification_code_pepper=_SECRET,
        )

        generic = await service.request_password_reset(email="unknown@x.com")
        response = await service.request_password_reset(email="activation-fail@x.com")

        assert response == generic
        assert await resets.get_active(email="activation-fail@x.com") is None

    asyncio.run(run())


def test_stale_token_renews_with_current_database_role() -> None:
    client, _, token_service, users, _, _ = _client()
    account = users._by_email["token-user@example.com"]
    object.__setattr__(account, "role", Role.MANAGER)

    response = client.get(
        "/me",
        headers={"Authorization": f"Bearer {_backdated_token(13)}"},
    )

    assert response.status_code == 200
    renewed = response.headers["X-Renewed-Token"]
    assert token_service.verify(renewed).role is Role.MANAGER


class _RecordingTokenService(TokenService):
    def __init__(self) -> None:
        self.issued: list[AuthUser] = []

    def issue(self, user: AuthUser) -> str:
        self.issued.append(user)
        return f"token-{len(self.issued)}"

    def verify(self, token: str) -> AuthUser:
        del token
        raise NotImplementedError

    def renew_if_stale(self, token: str, current_user: AuthUser) -> str | None:
        del token, current_user
        raise NotImplementedError


class _CountingPasswordHasher:
    def __init__(self) -> None:
        self.hash_calls: list[str] = []

    def hash(self, password: str) -> str:
        self.hash_calls.append(password)
        return f"hash:{password}"

    def verify(self, password: str, hashed: str) -> bool:
        return hashed == f"hash:{password}"


class _FakeRegistrationStore(RegistrationStore):
    def __init__(self, users: _FakeUserRepo) -> None:
        self._users = users
        self._current: dict[str, RegistrationChallenge] = {}
        self._items: dict[str, RegistrationChallenge] = {}
        self._sequence = 0
        self._lock = asyncio.Lock()
        self.force_invalid_completion = False
        self.invalidated_ids: list[str] = []
        self.invalidate_error: Exception | None = None
        self.activate_error: Exception | None = None
        self.activate_after_persist_error: Exception | None = None
        self.activation_returns_none = False
        self.completion_entries = 0
        self.successful_completions = 0
        self._completion_ready: asyncio.Event | None = None
        self._completion_release: asyncio.Event | None = None

    def current(self, email: str) -> RegistrationChallenge | None:
        return self._current.get(email)

    def _next_id(self, prefix: str) -> str:
        self._sequence += 1
        return f"{prefix}-{self._sequence:040d}"

    @staticmethod
    def _remaining(
        challenge: RegistrationChallenge,
        claimed_at: datetime,
        cooldown_seconds: int,
    ) -> int:
        previous = challenge.delivery_claimed_at
        if previous.tzinfo is None:
            previous = previous.replace(tzinfo=UTC)
        current = claimed_at if claimed_at.tzinfo is not None else claimed_at.replace(tzinfo=UTC)
        return max(0, int(cooldown_seconds - (current - previous).total_seconds() + 0.999999))

    async def claim_initial(
        self,
        *,
        email: str,
        name: str,
        password_hash: str,
        code_hash: str,
        expires_at: datetime,
        claimed_at: datetime,
        cooldown_seconds: int,
    ) -> InitialRegistrationClaim:
        async with self._lock:
            if await self._users.get_by_email(email) is not None:
                return RegistrationAlreadyRegistered()
            previous = self._current.get(email)
            if previous is not None:
                remaining = self._remaining(previous, claimed_at, cooldown_seconds)
                if remaining > 0:
                    return RegistrationCooldown(remaining)
                self._items[previous.id] = replace(
                    previous,
                    delivery_state=RegistrationDeliveryState.CONSUMED,
                    consumed_at=claimed_at,
                )
            challenge = RegistrationChallenge(
                id=self._next_id("registration"),
                delivery_id=self._next_id("delivery"),
                email=email,
                name=name,
                password_hash=password_hash,
                code_hash=code_hash,
                delivery_state=RegistrationDeliveryState.PENDING,
                expires_at=expires_at,
                attempt_count=0,
                created_at=claimed_at,
                delivery_claimed_at=claimed_at,
                activated_at=None,
                consumed_at=None,
            )
            self._current[email] = challenge
            self._items[challenge.id] = challenge
            return RegistrationClaimed(challenge)

    async def claim_resend(
        self,
        *,
        email: str,
        challenge_id: str,
        code_hash: str,
        expires_at: datetime,
        claimed_at: datetime,
        cooldown_seconds: int,
    ) -> ResendRegistrationClaim:
        async with self._lock:
            challenge = self._current.get(email)
            if (
                challenge is None
                or challenge.id != challenge_id
                or challenge.delivery_state is RegistrationDeliveryState.CONSUMED
            ):
                return RegistrationClaimInvalid()
            remaining = self._remaining(challenge, claimed_at, cooldown_seconds)
            if remaining > 0:
                return RegistrationCooldown(remaining)
            replacement = replace(
                challenge,
                id=self._next_id("registration"),
                delivery_id=self._next_id("delivery"),
                code_hash=code_hash,
                delivery_state=RegistrationDeliveryState.PENDING,
                expires_at=expires_at,
                attempt_count=0,
                delivery_claimed_at=claimed_at,
                activated_at=None,
            )
            self._items[challenge_id] = replace(
                challenge,
                delivery_state=RegistrationDeliveryState.CONSUMED,
                consumed_at=claimed_at,
            )
            self._current[email] = replacement
            self._items[replacement.id] = replacement
            return RegistrationClaimed(replacement)

    async def activate(
        self,
        *,
        challenge_id: str,
        delivery_id: str,
        activated_at: datetime,
    ) -> RegistrationChallenge | None:
        if self.activate_error is not None:
            raise self.activate_error
        if self.activation_returns_none:
            return None
        for email, challenge in self._current.items():
            if (
                challenge.id == challenge_id
                and challenge.delivery_id == delivery_id
                and challenge.delivery_state is RegistrationDeliveryState.PENDING
                and challenge.consumed_at is None
            ):
                active = replace(
                    challenge,
                    delivery_state=RegistrationDeliveryState.ACTIVE,
                    activated_at=activated_at,
                )
                self._current[email] = active
                self._items[challenge_id] = active
                if self.activate_after_persist_error is not None:
                    raise self.activate_after_persist_error
                return active
        return None

    async def get_active(
        self,
        *,
        email: str,
        challenge_id: str,
    ) -> RegistrationChallenge | None:
        challenge = self._current.get(email)
        if (
            challenge is None
            or challenge.id != challenge_id
            or challenge.delivery_state is not RegistrationDeliveryState.ACTIVE
            or challenge.consumed_at is not None
        ):
            return None
        return challenge

    async def record_failed_attempt(
        self,
        *,
        challenge_id: str,
        delivery_id: str,
    ) -> RegistrationChallenge | None:
        for email, challenge in self._current.items():
            if (
                challenge.id == challenge_id
                and challenge.delivery_id == delivery_id
                and challenge.delivery_state is RegistrationDeliveryState.ACTIVE
                and challenge.consumed_at is None
            ):
                updated = replace(challenge, attempt_count=challenge.attempt_count + 1)
                self._current[email] = updated
                self._items[challenge_id] = updated
                return updated
        return None

    async def invalidate(
        self,
        *,
        challenge_id: str,
        delivery_id: str,
        invalidated_at: datetime,
    ) -> bool:
        if self.invalidate_error is not None:
            raise self.invalidate_error
        for email, challenge in self._current.items():
            if (
                challenge.id == challenge_id
                and challenge.delivery_id == delivery_id
                and challenge.consumed_at is None
            ):
                invalidated = replace(
                    challenge,
                    delivery_state=RegistrationDeliveryState.CONSUMED,
                    consumed_at=invalidated_at,
                )
                self._current[email] = invalidated
                self._items[challenge_id] = invalidated
                self.invalidated_ids.append(challenge_id)
                return True
        return False

    async def complete(
        self,
        *,
        expected: RegistrationChallenge,
        completed_at: datetime,
    ) -> RegistrationCompletion:
        self.completion_entries += 1
        if self._completion_ready is not None and self._completion_release is not None:
            if self.completion_entries == 2:
                self._completion_ready.set()
            await self._completion_release.wait()
        async with self._lock:
            current = self._current.get(expected.email)
            expires_at = expected.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if (
                self.force_invalid_completion
                or current != expected
                or expected.delivery_state is not RegistrationDeliveryState.ACTIVE
                or expected.consumed_at is not None
                or expires_at <= completed_at
            ):
                return RegistrationInvalid()
            if await self._users.get_by_email(expected.email) is not None:
                return RegistrationDuplicate()
            account = await self._users.add(
                email=expected.email,
                password_hash=expected.password_hash,
                name=expected.name,
                role=Role.DESIGNER,
            )
            consumed = replace(
                current,
                delivery_state=RegistrationDeliveryState.CONSUMED,
                consumed_at=completed_at,
            )
            self._current[expected.email] = consumed
            self._items[expected.id] = consumed
            self.successful_completions += 1
            return RegistrationCompleted(account)

    def set_current(self, challenge: RegistrationChallenge) -> None:
        self._current[challenge.email] = challenge
        self._items[challenge.id] = challenge

    def block_two_completions(self) -> None:
        self._completion_ready = asyncio.Event()
        self._completion_release = asyncio.Event()

    async def wait_for_two_completion_entries(self) -> None:
        assert self._completion_ready is not None
        await self._completion_ready.wait()

    def release_completions(self) -> None:
        assert self._completion_release is not None
        self._completion_release.set()


class _SwitchableMailer(MailPort):
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []
        self.should_fail = False

    async def send(self, *, to: str, subject: str, body_text: str) -> None:
        if self.should_fail:
            raise OSError("smtp unavailable")
        self.sent.append((to, subject, body_text))


def _registration_code(mailer: _SwitchableMailer) -> str:
    assert mailer.sent
    match = re.search(r"(?<!\d)(\d{6})(?!\d)", mailer.sent[-1][2])
    assert match is not None
    return match.group(1)


def _registration_service() -> tuple[
    AccountService,
    _FakeUserRepo,
    _FakeRegistrationStore,
    _SwitchableMailer,
    _CountingPasswordHasher,
    _RecordingTokenService,
]:
    users = _FakeUserRepo()
    registrations = _FakeRegistrationStore(users)
    mailer = _SwitchableMailer()
    passwords = _CountingPasswordHasher()
    tokens = _RecordingTokenService()
    return (
        AccountService(
            users=users,
            passwords=passwords,
            tokens=tokens,
            mailer=mailer,
            registrations=registrations,
            email_verification_code_pepper=_SECRET,
            registration_code_ttl_seconds=300,
            registration_resend_cooldown_seconds=60,
            registration_max_attempts=2,
        ),
        users,
        registrations,
        mailer,
        passwords,
        tokens,
    )


def test_request_registration_keeps_identity_pending_without_jwt() -> None:
    async def run() -> None:
        service, users, registrations, mailer, passwords, tokens = _registration_service()

        challenge_id = await service.request_registration(
            email="  pending@example.com ", password="password88", name="  Pending User  "
        )

        challenge = await registrations.get_active(
            email="pending@example.com",
            challenge_id=challenge_id,
        )
        assert await users.get_by_email("pending@example.com") is None
        assert challenge is not None
        assert challenge.name == "Pending User"
        assert challenge.password_hash == "hash:password88"
        assert challenge.code_hash != _registration_code(mailer)
        assert passwords.hash_calls == ["password88"]
        assert tokens.issued == []

    asyncio.run(run())


def test_verify_registration_creates_account_then_issues_jwt() -> None:
    async def run() -> None:
        service, users, registrations, mailer, _, tokens = _registration_service()
        challenge_id = await service.request_registration(
            email="verify@example.com", password="password88", name="Verifier"
        )

        token, user = await service.verify_registration(
            email="verify@example.com",
            challenge_id=challenge_id,
            code=_registration_code(mailer),
        )

        assert token == "token-1"
        assert user.user_id == "1"
        assert (await users.get_by_email("verify@example.com")) is not None
        assert (
            await registrations.get_active(
                email="verify@example.com",
                challenge_id=challenge_id,
            )
            is None
        )
        assert tokens.issued == [user]

    asyncio.run(run())


def test_pending_registration_cannot_log_in() -> None:
    async def run() -> None:
        service, _, _, _, _, tokens = _registration_service()
        await service.request_registration(
            email="pending-login@example.com", password="password88", name="Pending"
        )

        with pytest.raises(AuthenticationError):
            await service.login(email="pending-login@example.com", password="password88")
        assert tokens.issued == []

    asyncio.run(run())


def test_request_registration_rejects_already_registered_email() -> None:
    async def run() -> None:
        service, users, registrations, mailer, passwords, _ = _registration_service()
        await users.add(
            email="duplicate@example.com",
            password_hash="hash:existing",
            name="Existing",
            role=Role.DESIGNER,
        )

        with pytest.raises(DomainError):
            await service.request_registration(
                email="duplicate@example.com", password="password88", name="Duplicate"
            )
        assert registrations.current("duplicate@example.com") is None
        assert mailer.sent == []
        assert passwords.hash_calls == ["password88"]

    asyncio.run(run())


@pytest.mark.parametrize("code", ["12345", "1234567", "abc123"])
def test_verify_registration_rejects_malformed_codes_with_generic_message(code: str) -> None:
    async def run() -> None:
        service, _, registrations, _, _, tokens = _registration_service()
        challenge_id = await service.request_registration(
            email="malformed@example.com", password="password88", name="Malformed"
        )

        with pytest.raises(ValueError, match="验证码错误或已过期"):
            await service.verify_registration(
                email="malformed@example.com",
                challenge_id=challenge_id,
                code=code,
            )
        challenge = await registrations.get_active(
            email="malformed@example.com",
            challenge_id=challenge_id,
        )
        assert challenge is not None and challenge.attempt_count == 0
        assert tokens.issued == []

    asyncio.run(run())


def test_verify_registration_expired_code_uses_generic_message() -> None:
    async def run() -> None:
        service, _, registrations, mailer, _, tokens = _registration_service()
        challenge_id = await service.request_registration(
            email="expired@example.com", password="password88", name="Expired"
        )
        challenge = await registrations.get_active(
            email="expired@example.com",
            challenge_id=challenge_id,
        )
        assert challenge is not None
        registrations.set_current(
            replace(challenge, expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )

        with pytest.raises(ValueError, match="验证码错误或已过期"):
            await service.verify_registration(
                email="expired@example.com",
                challenge_id=challenge_id,
                code=_registration_code(mailer),
            )
        assert tokens.issued == []

    asyncio.run(run())


def test_verify_registration_treats_naive_expiry_as_utc() -> None:
    async def run() -> None:
        service, _, registrations, mailer, _, tokens = _registration_service()
        challenge_id = await service.request_registration(
            email="naive-expiry@example.com", password="password88", name="Naive Expiry"
        )
        challenge = await registrations.get_active(
            email="naive-expiry@example.com",
            challenge_id=challenge_id,
        )
        assert challenge is not None
        expired_naive_utc = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
        registrations.set_current(replace(challenge, expires_at=expired_naive_utc))

        with pytest.raises(ValueError, match="验证码错误或已过期"):
            await service.verify_registration(
                email="naive-expiry@example.com",
                challenge_id=challenge_id,
                code=_registration_code(mailer),
            )
        assert tokens.issued == []

    asyncio.run(run())


def test_verify_registration_exhausted_attempts_uses_generic_message() -> None:
    async def run() -> None:
        service, _, registrations, mailer, _, tokens = _registration_service()
        challenge_id = await service.request_registration(
            email="exhausted@example.com", password="password88", name="Exhausted"
        )
        challenge = await registrations.get_active(
            email="exhausted@example.com",
            challenge_id=challenge_id,
        )
        assert challenge is not None
        registrations.set_current(replace(challenge, attempt_count=2))

        with pytest.raises(ValueError, match="验证码错误或已过期"):
            await service.verify_registration(
                email="exhausted@example.com",
                challenge_id=challenge_id,
                code=_registration_code(mailer),
            )
        assert tokens.issued == []

    asyncio.run(run())


def test_verify_registration_rejects_after_max_attempt_is_reached() -> None:
    async def run() -> None:
        service, _, registrations, mailer, _, tokens = _registration_service()
        challenge_id = await service.request_registration(
            email="max-attempt@example.com", password="password88", name="Max Attempt"
        )
        code = _registration_code(mailer)
        wrong = f"{(int(code) + 1) % 1_000_000:06d}"

        for _ in range(2):
            with pytest.raises(ValueError, match="验证码错误或已过期"):
                await service.verify_registration(
                    email="max-attempt@example.com",
                    challenge_id=challenge_id,
                    code=wrong,
                )

        challenge = await registrations.get_active(
            email="max-attempt@example.com",
            challenge_id=challenge_id,
        )
        assert challenge is not None and challenge.attempt_count == 2
        with pytest.raises(ValueError, match="验证码错误或已过期"):
            await service.verify_registration(
                email="max-attempt@example.com",
                challenge_id=challenge_id,
                code=code,
            )
        assert tokens.issued == []

    asyncio.run(run())


def test_verify_registration_wrong_code_records_attempt_and_uses_generic_message() -> None:
    async def run() -> None:
        service, _, registrations, mailer, _, tokens = _registration_service()
        challenge_id = await service.request_registration(
            email="wrong@example.com", password="password88", name="Wrong"
        )
        code = _registration_code(mailer)
        wrong = f"{(int(code) + 1) % 1_000_000:06d}"

        with pytest.raises(ValueError, match="验证码错误或已过期"):
            await service.verify_registration(
                email="wrong@example.com",
                challenge_id=challenge_id,
                code=wrong,
            )
        challenge = await registrations.get_active(
            email="wrong@example.com",
            challenge_id=challenge_id,
        )
        assert challenge is not None and challenge.attempt_count == 1
        assert tokens.issued == []

    asyncio.run(run())


def test_resend_registration_enforces_cooldown() -> None:
    async def run() -> None:
        service, _, registrations, _, _, _ = _registration_service()
        challenge_id = await service.request_registration(
            email="cooldown@example.com", password="password88", name="Cooldown"
        )
        original = await registrations.get_active(
            email="cooldown@example.com",
            challenge_id=challenge_id,
        )
        assert original is not None

        with pytest.raises(ValueError):
            await service.resend_registration(
                email="cooldown@example.com",
                challenge_id=challenge_id,
            )
        assert (
            await registrations.get_active(
                email="cooldown@example.com",
                challenge_id=challenge_id,
            )
            == original
        )

    asyncio.run(run())


def test_resend_registration_treats_naive_delivery_claimed_at_as_utc() -> None:
    async def run() -> None:
        service, _, registrations, _, _, _ = _registration_service()
        challenge_id = await service.request_registration(
            email="naive-sent@example.com", password="password88", name="Naive Sent"
        )
        challenge = await registrations.get_active(
            email="naive-sent@example.com",
            challenge_id=challenge_id,
        )
        assert challenge is not None
        registrations.set_current(
            replace(
                challenge,
                delivery_claimed_at=datetime.now(UTC).replace(tzinfo=None),
            )
        )

        with pytest.raises(ValueError):
            await service.resend_registration(
                email="naive-sent@example.com",
                challenge_id=challenge_id,
            )

    asyncio.run(run())


def test_resend_registration_replaces_code_and_rotates_pending_identity() -> None:
    async def run() -> None:
        service, _, registrations, mailer, _, _ = _registration_service()
        challenge_id = await service.request_registration(
            email="resend@example.com", password="password88", name="Resend"
        )
        original = await registrations.get_active(
            email="resend@example.com",
            challenge_id=challenge_id,
        )
        assert original is not None
        registrations.set_current(
            replace(
                original,
                delivery_claimed_at=datetime.now(UTC) - timedelta(seconds=61),
            )
        )

        returned_id = await service.resend_registration(
            email="resend@example.com",
            challenge_id=challenge_id,
        )

        replacement = await registrations.get_active(
            email="resend@example.com",
            challenge_id=returned_id,
        )
        assert replacement is not None
        assert returned_id != challenge_id
        assert replacement.id != original.id
        assert replacement.delivery_id != original.delivery_id
        assert replacement.name == original.name
        assert replacement.password_hash == original.password_hash
        assert len(mailer.sent) == 2

    asyncio.run(run())


def test_concurrent_resends_have_one_mail_sender() -> None:
    async def run() -> None:
        service, _, registrations, mailer, _, _ = _registration_service()
        challenge_id = await service.request_registration(
            email="resend-race@example.com",
            password="password88",
            name="Resend Race",
        )
        challenge = registrations.current("resend-race@example.com")
        assert challenge is not None
        registrations.set_current(
            replace(
                challenge,
                delivery_claimed_at=datetime.now(UTC) - timedelta(seconds=61),
            )
        )

        results = await asyncio.gather(
            service.resend_registration(
                email="resend-race@example.com",
                challenge_id=challenge_id,
            ),
            service.resend_registration(
                email="resend-race@example.com",
                challenge_id=challenge_id,
            ),
            return_exceptions=True,
        )

        returned_ids = [result for result in results if isinstance(result, str)]
        assert len(returned_ids) == 1
        assert returned_ids[0] != challenge_id
        assert sum(isinstance(result, ValueError) for result in results) == 1
        assert len(mailer.sent) == 2

    asyncio.run(run())


def test_verify_registration_rejects_superseded_code_with_generic_message() -> None:
    async def run() -> None:
        service, _, registrations, mailer, _, tokens = _registration_service()
        challenge_id = await service.request_registration(
            email="superseded@example.com", password="password88", name="Superseded"
        )
        original = await registrations.get_active(
            email="superseded@example.com",
            challenge_id=challenge_id,
        )
        assert original is not None
        old_code = _registration_code(mailer)
        registrations.set_current(
            replace(
                original,
                delivery_claimed_at=datetime.now(UTC) - timedelta(seconds=61),
            )
        )
        replacement_id = await service.resend_registration(
            email="superseded@example.com",
            challenge_id=challenge_id,
        )

        with pytest.raises(ValueError, match="验证码错误或已过期"):
            await service.verify_registration(
                email="superseded@example.com",
                challenge_id=challenge_id,
                code=old_code,
            )
        with pytest.raises(ValueError, match="验证码错误或已过期"):
            await service.verify_registration(
                email="superseded@example.com",
                challenge_id=replacement_id,
                code=old_code,
            )
        assert tokens.issued == []

    asyncio.run(run())


def test_initial_registration_delivery_failure_invalidates_challenge() -> None:
    async def run() -> None:
        service, _, registrations, mailer, _, _ = _registration_service()
        mailer.should_fail = True

        with pytest.raises(OSError, match="smtp unavailable"):
            await service.request_registration(
                email="initial-failure@example.com", password="password88", name="Initial"
            )
        failed = registrations.current("initial-failure@example.com")
        assert failed is not None
        assert failed.delivery_state is RegistrationDeliveryState.CONSUMED
        assert registrations.invalidated_ids == [failed.id]

    asyncio.run(run())


def test_registration_delivery_and_invalidation_failure_preserves_both_causes() -> None:
    async def run() -> None:
        service, _, registrations, mailer, _, _ = _registration_service()
        mailer.should_fail = True
        invalidation_error = OSError("registration store unavailable")
        registrations.invalidate_error = invalidation_error

        with pytest.raises(RegistrationDeliveryFailure) as raised:
            await service.request_registration(
                email="double-failure@example.com", password="password88", name="Double Failure"
            )

        error = raised.value
        assert "smtp unavailable" in str(error)
        assert "registration store unavailable" in str(error)
        assert isinstance(error.delivery_error, OSError)
        assert str(error.delivery_error) == "smtp unavailable"
        assert error.invalidation_error is invalidation_error
        assert error.__cause__ is invalidation_error
        assert invalidation_error.__context__ is error.delivery_error
        failed = registrations.current("double-failure@example.com")
        assert failed is not None
        assert failed.delivery_state is RegistrationDeliveryState.PENDING
        assert (
            await registrations.get_active(
                email=failed.email,
                challenge_id=failed.id,
            )
            is None
        )

    asyncio.run(run())


def test_activation_and_invalidation_failure_never_exposes_an_active_code() -> None:
    async def run() -> None:
        service, _, registrations, mailer, _, tokens = _registration_service()
        activation_error = OSError("activation unavailable")
        registrations.activate_error = activation_error
        registrations.invalidate_error = OSError("invalidation unavailable")

        with pytest.raises(RuntimeError, match="activation"):
            await service.request_registration(
                email="activation-double-failure@example.com",
                password="password88",
                name="Activation Double Failure",
            )

        failed = registrations.current("activation-double-failure@example.com")
        assert failed is not None
        assert failed.delivery_state is RegistrationDeliveryState.PENDING
        assert (
            await registrations.get_active(
                email=failed.email,
                challenge_id=failed.id,
            )
            is None
        )
        assert len(mailer.sent) == 1
        assert tokens.issued == []

    asyncio.run(run())


def test_ambiguous_resend_activation_failure_does_not_expose_identity() -> None:
    async def run() -> None:
        service, _, registrations, mailer, _, tokens = _registration_service()
        original_id = await service.request_registration(
            email="ambiguous-resend@example.com",
            password="password88",
            name="Ambiguous Resend",
        )
        original = registrations.current("ambiguous-resend@example.com")
        assert original is not None
        registrations.set_current(
            replace(
                original,
                delivery_claimed_at=datetime.now(UTC) - timedelta(seconds=61),
            )
        )
        registrations.activate_after_persist_error = OSError("activation result unavailable")
        registrations.invalidate_error = OSError("invalidation unavailable")

        with pytest.raises(RegistrationActivationFailure):
            await service.resend_registration(
                email="ambiguous-resend@example.com",
                challenge_id=original_id,
            )

        assert (
            await registrations.get_active(
                email="ambiguous-resend@example.com",
                challenge_id=original_id,
            )
            is None
        )
        assert len(mailer.sent) == 2
        assert tokens.issued == []

    asyncio.run(run())


def test_new_registration_identity_prevents_old_browser_from_verifying_replacement() -> None:
    async def run() -> None:
        service, users, registrations, mailer, _, tokens = _registration_service()
        first_id = await service.request_registration(
            email="shared@example.com",
            password="victim-password",
            name="Victim",
        )
        first_code = _registration_code(mailer)
        first = registrations.current("shared@example.com")
        assert first is not None
        registrations.set_current(
            replace(
                first,
                delivery_claimed_at=datetime.now(UTC) - timedelta(seconds=61),
            )
        )

        second_id = await service.request_registration(
            email="shared@example.com",
            password="attacker-password",
            name="Attacker",
        )

        assert second_id != first_id
        with pytest.raises(ValueError, match="验证码错误或已过期"):
            await service.verify_registration(
                email="shared@example.com",
                challenge_id=first_id,
                code=first_code,
            )
        assert await users.get_by_email("shared@example.com") is None
        assert tokens.issued == []

    asyncio.run(run())


def test_concurrent_initial_requests_have_one_mail_sender() -> None:
    async def run() -> None:
        service, _, _, mailer, _, _ = _registration_service()
        results = await asyncio.gather(
            service.request_registration(
                email="claim-race@example.com",
                password="password88",
                name="First",
            ),
            service.request_registration(
                email="claim-race@example.com",
                password="password99",
                name="Second",
            ),
            return_exceptions=True,
        )

        assert sum(isinstance(result, str) for result in results) == 1
        assert sum(isinstance(result, ValueError) for result in results) == 1
        assert len(mailer.sent) == 1

    asyncio.run(run())


def test_resend_delivery_failure_invalidates_replacement_without_restoring_old_code() -> None:
    async def run() -> None:
        service, _, registrations, _, _, _ = _registration_service()
        challenge_id = await service.request_registration(
            email="resend-failure@example.com", password="password88", name="Resend Failure"
        )
        original = await registrations.get_active(
            email="resend-failure@example.com",
            challenge_id=challenge_id,
        )
        assert original is not None
        registrations.set_current(
            replace(
                original,
                delivery_claimed_at=datetime.now(UTC) - timedelta(seconds=61),
            )
        )
        mailer = service.mailer
        assert isinstance(mailer, _SwitchableMailer)
        mailer.should_fail = True

        with pytest.raises(OSError, match="smtp unavailable"):
            await service.resend_registration(
                email="resend-failure@example.com",
                challenge_id=challenge_id,
            )
        assert (
            await registrations.get_active(
                email="resend-failure@example.com",
                challenge_id=challenge_id,
            )
            is None
        )
        assert len(registrations.invalidated_ids) == 1
        assert registrations.invalidated_ids[0] != challenge_id

    asyncio.run(run())


def test_verify_registration_issues_no_token_when_atomic_completion_rejects() -> None:
    async def run() -> None:
        service, _, registrations, mailer, _, tokens = _registration_service()
        challenge_id = await service.request_registration(
            email="atomic-invalid@example.com", password="password88", name="Atomic"
        )
        registrations.force_invalid_completion = True

        with pytest.raises(ValueError, match="验证码错误或已过期"):
            await service.verify_registration(
                email="atomic-invalid@example.com",
                challenge_id=challenge_id,
                code=_registration_code(mailer),
            )
        assert tokens.issued == []

    asyncio.run(run())


def test_verify_registration_maps_atomic_duplicate_without_issuing_token() -> None:
    async def run() -> None:
        service, users, _, mailer, _, tokens = _registration_service()
        challenge_id = await service.request_registration(
            email="atomic-duplicate@example.com", password="password88", name="Atomic"
        )
        await users.add(
            email="atomic-duplicate@example.com",
            password_hash="hash:existing",
            name="Existing",
            role=Role.DESIGNER,
        )

        with pytest.raises(DomainError):
            await service.verify_registration(
                email="atomic-duplicate@example.com",
                challenge_id=challenge_id,
                code=_registration_code(mailer),
            )
        assert tokens.issued == []

    asyncio.run(run())


def test_concurrent_registration_verification_has_one_winner() -> None:
    async def run() -> None:
        service, users, registrations, mailer, _, tokens = _registration_service()
        challenge_id = await service.request_registration(
            email="race@example.com", password="password88", name="Race"
        )
        code = _registration_code(mailer)
        registrations.block_two_completions()
        first = asyncio.create_task(
            service.verify_registration(
                email="race@example.com",
                challenge_id=challenge_id,
                code=code,
            ),
        )
        second = asyncio.create_task(
            service.verify_registration(
                email="race@example.com",
                challenge_id=challenge_id,
                code=code,
            ),
        )
        await asyncio.wait_for(registrations.wait_for_two_completion_entries(), timeout=1)
        assert registrations.completion_entries == 2
        registrations.release_completions()
        results = await asyncio.gather(first, second, return_exceptions=True)

        assert sum(isinstance(result, tuple) for result in results) == 1
        assert sum(isinstance(result, ValueError) for result in results) == 1
        assert await users.get_by_email("race@example.com") is not None
        assert registrations.successful_completions == 1
        assert len(tokens.issued) == 1

    asyncio.run(run())
