"""登录健壮性（ISSUE-0058）：滑动续期 + 密码传输公钥加密。

单元：jwt renew_if_stale（半衰期前/后/过期）、RSA cipher 往返/垃圾/from_pem。
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

from design_hub.application.auth.account_service import AccountService
from design_hub.domain.enums import Role
from design_hub.domain.errors import AuthenticationError
from design_hub.domain.models import AuthUser
from design_hub.infrastructure.auth.jwt_service import PyJwtTokenService
from design_hub.infrastructure.auth.password import BcryptPasswordHasher
from design_hub.infrastructure.auth.rsa_cipher import RsaPasswordCipher
from design_hub.interface.api.app import register_error_handlers
from design_hub.interface.api.routes import auth
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
    assert svc.renew_if_stale(_backdated_token(1)) is None  # 1h < 12h 半衰期


def test_renew_if_stale_past_halflife_issues_new_valid_token() -> None:
    svc = PyJwtTokenService(secret=_SECRET, renew_after_hours=12)
    tok = _backdated_token(13)  # 13h 老、仍未过期(exp=iat+24=now+11h)
    new = svc.renew_if_stale(tok)
    assert new is not None and new != tok  # iat 差 13h → 新令牌不同
    assert svc.verify(new).user_id == "7"
    assert svc.renew_if_stale(new) is None  # 新令牌 fresh、不再续


def test_verify_expired_raises() -> None:
    svc = PyJwtTokenService(secret=_SECRET, renew_after_hours=12)
    with pytest.raises(AuthenticationError):
        svc.verify(_backdated_token(30))  # exp=iat+24=now-6h 已过期


# ── 单元：RSA 密码传输加密 ────────────────────────────────────────────────


def test_rsa_round_trip_and_pubkey_is_spki() -> None:
    c = RsaPasswordCipher.generate()
    assert c.decrypt(c.encrypt("hunter2secret")) == "hunter2secret"
    assert c.public_key_pem().startswith("-----BEGIN PUBLIC KEY-----")


def test_rsa_decrypt_garbage_raises_valueerror_human() -> None:
    c = RsaPasswordCipher.generate()
    with pytest.raises(ValueError) as ei:
        c.decrypt("!!!not-base64-or-cipher!!!")
    assert "解密失败" in str(ei.value) and "500" not in str(ei.value)


def test_rsa_from_pem_loads_and_decrypts() -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    c = RsaPasswordCipher.from_pem(pem)
    assert c.decrypt(c.encrypt("secret123")) == "secret123"


def test_rsa_from_pem_tolerates_escaped_newlines() -> None:
    # docker env-file 单行 PEM（\n 字面转义）也能 load（coordinator #1024 部署前置必修）
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    single_line = pem.replace("\n", "\\n")  # 真实换行 → `\n` 字面（模拟 env 单行携带）
    assert "\n" not in single_line.replace("\\n", "")  # 确认已无真实换行
    c = RsaPasswordCipher.from_pem(single_line)
    assert c.decrypt(c.encrypt("secret123")) == "secret123"


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

    async def set_role(self, user_id: int, role: Role) -> UserAccount:
        raise NotImplementedError

    async def list_all(self) -> list[UserAccount]:
        return list(self._by_email.values())

    async def count_by_role(self, role: Role) -> int:
        return sum(1 for a in self._by_email.values() if a.role == role)


def _client() -> tuple[TestClient, RsaPasswordCipher, PyJwtTokenService]:
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(auth.router)
    token_service = PyJwtTokenService(secret=_SECRET, renew_after_hours=12)
    cipher = RsaPasswordCipher.generate()
    app.state.token_service = token_service
    app.state.password_cipher = cipher
    app.state.account_service = AccountService(
        users=_FakeUserRepo(), passwords=BcryptPasswordHasher(), tokens=token_service
    )
    return TestClient(app), cipher, token_service


def test_pubkey_returns_spki_pem() -> None:
    client, _, _ = _client()
    resp = client.get("/auth/pubkey")
    assert resp.status_code == 200
    assert resp.json()["public_key"].startswith("-----BEGIN PUBLIC KEY-----")


def test_register_login_round_trip_encrypted_password() -> None:
    client, cipher, _ = _client()
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


def test_login_garbage_ciphertext_400_no_plaintext_leak() -> None:
    client, _, _ = _client()
    resp = client.post("/auth/login", json={"email": "a@b.com", "password": "garbage-not-cipher"})
    assert resp.status_code == 400


def test_register_short_plaintext_400_checked_after_decrypt() -> None:
    # 明文长度校验挪到解密后：密文合法但明文<8 → 400（不是密文长度）
    client, cipher, _ = _client()
    resp = client.post(
        "/auth/register",
        json={"email": "c@d.com", "name": "C", "password": cipher.encrypt("short")},
    )
    assert resp.status_code == 400


def test_me_stale_token_returns_renewed_header() -> None:
    client, _, token_service = _client()
    resp = client.get("/me", headers={"Authorization": f"Bearer {_backdated_token(13)}"})
    assert resp.status_code == 200
    assert "X-Renewed-Token" in resp.headers
    assert token_service.verify(resp.headers["X-Renewed-Token"]).user_id == "7"


def test_me_fresh_token_no_renewed_header() -> None:
    client, _, token_service = _client()
    fresh = token_service.issue(AuthUser(user_id="7", name="t", role=Role.DESIGNER, dept=None))
    resp = client.get("/me", headers={"Authorization": f"Bearer {fresh}"})
    assert resp.status_code == 200 and "X-Renewed-Token" not in resp.headers


def test_me_expired_token_401_no_renewal() -> None:
    client, _, _ = _client()
    resp = client.get("/me", headers={"Authorization": f"Bearer {_backdated_token(30)}"})
    assert resp.status_code == 401 and "X-Renewed-Token" not in resp.headers
