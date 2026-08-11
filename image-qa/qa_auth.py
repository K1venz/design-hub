from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from enum import StrEnum

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

_OAEP = padding.OAEP(
    mgf=padding.MGF1(hashes.SHA256()),
    algorithm=hashes.SHA256(),
    label=None,
)


class AccountSlot(StrEnum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    ADMIN = "admin"


@dataclass(frozen=True, slots=True)
class AuthSession:
    email: str
    jwt: str


_ACCOUNT_ENV = {
    AccountSlot.PRIMARY: ("QA_USER_EMAIL", "QA_USER_PASSWORD"),
    AccountSlot.SECONDARY: (
        "QA_SECONDARY_USER_EMAIL",
        "QA_SECONDARY_USER_PASSWORD",
    ),
    AccountSlot.ADMIN: ("ADMIN_EMAIL", "ADMIN_PASSWORD"),
}


def _runtime_credentials(slot: AccountSlot) -> tuple[str, str]:
    email_key, password_key = _ACCOUNT_ENV[slot]
    email = os.environ.get(email_key, "").strip()
    password = os.environ.get(password_key, "")
    if not email or not password:
        raise RuntimeError(
            f"{email_key} and {password_key} must identify a pre-verified QA account"
        )
    return email, password


async def encrypt_password(
    client: httpx.AsyncClient,
    password: str,
    *,
    prefix: str = "",
) -> str:
    response = await client.get(f"{prefix}/auth/pubkey")
    response.raise_for_status()
    public_key_pem = response.json().get("public_key")
    if not isinstance(public_key_pem, str) or not public_key_pem:
        raise RuntimeError("Public-key response did not contain public_key")
    public_key = serialization.load_pem_public_key(public_key_pem.encode("ascii"))
    if not isinstance(public_key, rsa.RSAPublicKey):
        raise RuntimeError("Authentication public key is not RSA")
    ciphertext = public_key.encrypt(password.encode("utf-8"), _OAEP)
    return base64.b64encode(ciphertext).decode("ascii")


async def login_verified_account(
    client: httpx.AsyncClient,
    *,
    prefix: str = "",
    slot: AccountSlot = AccountSlot.PRIMARY,
) -> AuthSession:
    email, password = _runtime_credentials(slot)
    encrypted_password = await encrypt_password(client, password, prefix=prefix)
    response = await client.post(
        f"{prefix}/auth/login",
        json={"email": email, "password": encrypted_password},
    )
    response.raise_for_status()
    jwt = response.json().get("jwt")
    if not isinstance(jwt, str) or not jwt:
        raise RuntimeError("Login response did not contain a non-empty jwt")
    return AuthSession(email=email, jwt=jwt)
