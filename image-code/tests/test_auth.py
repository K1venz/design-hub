"""登录健壮性（ISSUE-0058）：滑动续期 + 密码传输公钥加密。

单元：jwt renew_if_stale（半衰期前/后/过期）。
集成（TestClient + 假 repo + 真 cipher/token）：/auth/pubkey、密文注册登录往返、
解密失败 400、明文<8 → 400、/me 过半衰期回 X-Renewed-Token、fresh 无头、过期 401。
"""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient

from design_hub.application.auth.account_service import AccountService, _hash_reset_code
from design_hub.domain.enums import Role
from design_hub.domain.errors import AuthenticationError, NotFoundError
from design_hub.domain.models import AuthUser
from design_hub.infrastructure.auth.jwt_service import PyJwtTokenService
from design_hub.infrastructure.auth.password import BcryptPasswordHasher
from design_hub.infrastructure.security.rsa_secret_cipher import RsaSecretCipher
from design_hub.interface.api.app import register_error_handlers
from design_hub.interface.api.deps import CurrentUserSseDep
from design_hub.interface.api.routes import auth
from design_hub.ports.mail import MailPort
from design_hub.ports.password_reset import PasswordResetChallenge, PasswordResetStore
from design_hub.ports.user_repository import UserAccount, UserRepository

_SECRET = "test-secret-min-32-bytes-aaaaaaaaaaaa"


def _backdated_token(iat_hours_ago: float, ttl_hours: int = 24) -> str:
    iat = datetime.now(UTC) - timedelta(hours=iat_hours_ago)
    payload = {
        "sub": "7", "name": "t", "role": Role.DESIGNER.value, "dept": None,
        "iat": iat, "exp": iat + timedelta(hours=ttl_hours),
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

    async def add(
        self, *, email: str, password_hash: str, name: str, role: Role
    ) -> UserAccount:
        self._seq += 1
        acc = UserAccount(
            id=self._seq, email=email, name=name, role=role,
            created_at=datetime.now(UTC), password_hash=password_hash,
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


class _FakeResetStore(PasswordResetStore):
    def __init__(self) -> None:
        self._items: dict[str, PasswordResetChallenge] = {}

    async def get_active(self, email: str) -> PasswordResetChallenge | None:
        return self._items.get(email)

    async def replace_active(
        self,
        *,
        email: str,
        code_hash: str,
        expires_at: datetime,
    ) -> PasswordResetChallenge:
        ch = PasswordResetChallenge(
            id=f"ch-{email}",
            email=email,
            code_hash=code_hash,
            expires_at=expires_at,
            attempt_count=0,
            created_at=datetime.now(UTC),
            consumed_at=None,
        )
        self._items[email] = ch
        return ch

    async def record_failed_attempt(self, challenge_id: str) -> PasswordResetChallenge | None:
        for email, ch in list(self._items.items()):
            if ch.id == challenge_id and ch.consumed_at is None:
                updated = PasswordResetChallenge(
                    id=ch.id,
                    email=ch.email,
                    code_hash=ch.code_hash,
                    expires_at=ch.expires_at,
                    attempt_count=ch.attempt_count + 1,
                    created_at=ch.created_at,
                    consumed_at=None,
                )
                self._items[email] = updated
                return updated
        return None

    async def consume(self, challenge_id: str) -> None:
        for email, ch in list(self._items.items()):
            if ch.id == challenge_id:
                self._items[email] = PasswordResetChallenge(
                    id=ch.id,
                    email=ch.email,
                    code_hash=ch.code_hash,
                    expires_at=ch.expires_at,
                    attempt_count=ch.attempt_count,
                    created_at=ch.created_at,
                    consumed_at=datetime.now(UTC),
                )


def _client() -> tuple[
    TestClient,
    RsaSecretCipher,
    PyJwtTokenService,
    _FakeUserRepo,
    _FakeMailer,
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
    mailer = _FakeMailer()
    resets = _FakeResetStore()
    app.state.account_service = AccountService(
        users=users,
        passwords=BcryptPasswordHasher(),
        tokens=token_service,
        resets=resets,
        mailer=mailer,
        reset_code_pepper=_SECRET,
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


def test_register_login_round_trip_encrypted_password() -> None:
    client, cipher, _, _, _, _ = _client()
    reg = client.post(
        "/auth/register",
        json={"email": "a@b.com", "name": "A", "password": cipher.encrypt("mypassword8")},
    )
    assert reg.status_code == 200 and reg.json()["jwt"]
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


def test_register_short_plaintext_400_checked_after_decrypt() -> None:
    # 明文长度校验挪到解密后：密文合法但明文<8 → 400（不是密文长度）
    client, cipher, _, _, _, _ = _client()
    resp = client.post(
        "/auth/register",
        json={"email": "c@d.com", "name": "C", "password": cipher.encrypt("short")},
    )
    assert resp.status_code == 400


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
    token = token_service.issue(
        AuthUser(user_id="7", name="t", role=Role.DESIGNER, dept=None)
    )

    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.json()["error"] == "unauthenticated"


def test_disabled_sse_token_is_rejected_on_next_request() -> None:
    client, _, token_service, users, _, _ = _client()
    account = users._by_email["token-user@example.com"]
    object.__setattr__(account, "enabled", False)
    token = token_service.issue(
        AuthUser(user_id="7", name="t", role=Role.DESIGNER, dept=None)
    )

    response = client.get(f"/test/sse-auth?access_token={token}")

    assert response.status_code == 401
    assert response.json()["error"] == "unauthenticated"


def test_disabled_user_cannot_log_in_again() -> None:
    client, cipher, _, users, _, _ = _client()
    registered = client.post(
        "/auth/register",
        json={
            "email": "disabled@example.com",
            "name": "Disabled",
            "password": cipher.encrypt("mypassword8"),
        },
    )
    assert registered.status_code == 200
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
    client, cipher, _, _, mailer, _ = _client()
    reg = client.post(
        "/auth/register",
        json={
            "email": "reset@x.com",
            "name": "R",
            "password": cipher.encrypt("oldpassword1"),
        },
    )
    assert reg.status_code == 200

    forgot = client.post("/auth/forgot-password", json={"email": "reset@x.com"})
    assert forgot.status_code == 200
    code = _code_from_mail(mailer)

    reset = client.post(
        "/auth/reset-password",
        json={
            "email": "reset@x.com",
            "code": code,
            "password": cipher.encrypt("newpassword9"),
        },
    )
    assert reset.status_code == 200

    bad_old = client.post(
        "/auth/login",
        json={"email": "reset@x.com", "password": cipher.encrypt("oldpassword1")},
    )
    assert bad_old.status_code == 401

    ok_new = client.post(
        "/auth/login",
        json={"email": "reset@x.com", "password": cipher.encrypt("newpassword9")},
    )
    assert ok_new.status_code == 200 and ok_new.json()["jwt"]


def test_password_reset_wrong_code_400() -> None:
    client, cipher, _, _, mailer, _ = _client()
    client.post(
        "/auth/register",
        json={
            "email": "wrong@x.com",
            "name": "W",
            "password": cipher.encrypt("oldpassword1"),
        },
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
    client, cipher, _, _, _, _ = _client()
    client.post(
        "/auth/register",
        json={
            "email": "cool@x.com",
            "name": "C",
            "password": cipher.encrypt("oldpassword1"),
        },
    )
    assert client.post("/auth/forgot-password", json={"email": "cool@x.com"}).status_code == 200
    again = client.post("/auth/forgot-password", json={"email": "cool@x.com"})
    assert again.status_code == 400
    assert "频繁" in again.json()["detail"]


def test_hash_reset_code_stable() -> None:
    a = _hash_reset_code(email="A@X.com", code="123456", pepper="p")
    b = _hash_reset_code(email="a@x.com", code="123456", pepper="p")
    assert a == b
    assert a != _hash_reset_code(email="a@x.com", code="123457", pepper="p")


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
