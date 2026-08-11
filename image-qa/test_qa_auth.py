from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import Iterator
from functools import wraps
from typing import Any

import httpx
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from qa_auth import AccountSlot, login_verified_account
from registration_acceptance import complete_registration

_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PUBLIC_KEY_PEM = (
    _PRIVATE_KEY.public_key()
    .public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    .decode("ascii")
)
_OAEP = padding.OAEP(
    mgf=padding.MGF1(hashes.SHA256()),
    algorithm=hashes.SHA256(),
    label=None,
)


def _async_test(function: Any) -> Any:
    @wraps(function)
    def run(*args: Any, **kwargs: Any) -> Any:
        return asyncio.run(function(*args, **kwargs))

    return run


def _json_body(request: httpx.Request) -> dict[str, str]:
    return json.loads(request.content.decode("utf-8"))


def _decrypt_password(request: httpx.Request) -> str:
    ciphertext = base64.b64decode(_json_body(request)["password"], validate=True)
    return _PRIVATE_KEY.decrypt(ciphertext, _OAEP).decode("utf-8")


@_async_test
async def test_login_uses_runtime_primary_account_without_registration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QA_USER_EMAIL", "verified@example.com")
    monkeypatch.setenv("QA_USER_PASSWORD", "runtime-secret")
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/auth/pubkey":
            return httpx.Response(
                200,
                json={"public_key": _PUBLIC_KEY_PEM},
                request=request,
            )
        assert _decrypt_password(request) == "runtime-secret"
        return httpx.Response(
            200,
            json={"jwt": "primary-token", "role": "设计师"},
            request=request,
        )

    async with httpx.AsyncClient(
        base_url="https://qa.example",
        transport=httpx.MockTransport(handler),
    ) as client:
        session = await login_verified_account(client, prefix="/api")

    assert session.email == "verified@example.com"
    assert session.jwt == "primary-token"
    assert [(request.method, request.url.path) for request in requests] == [
        ("GET", "/api/auth/pubkey"),
        ("POST", "/api/auth/login"),
    ]
    assert _json_body(requests[1])["email"] == "verified@example.com"


@_async_test
async def test_login_uses_runtime_secondary_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QA_SECONDARY_USER_EMAIL", "second@example.com")
    monkeypatch.setenv("QA_SECONDARY_USER_PASSWORD", "second-secret")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/pubkey":
            return httpx.Response(
                200,
                json={"public_key": _PUBLIC_KEY_PEM},
                request=request,
            )
        assert _json_body(request)["email"] == "second@example.com"
        assert _decrypt_password(request) == "second-secret"
        return httpx.Response(200, json={"jwt": "secondary-token"}, request=request)

    async with httpx.AsyncClient(
        base_url="https://qa.example",
        transport=httpx.MockTransport(handler),
    ) as client:
        session = await login_verified_account(client, slot=AccountSlot.SECONDARY)

    assert session.email == "second@example.com"
    assert session.jwt == "secondary-token"


@_async_test
async def test_login_uses_runtime_admin_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "admin-secret")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/pubkey":
            return httpx.Response(
                200,
                json={"public_key": _PUBLIC_KEY_PEM},
                request=request,
            )
        assert _json_body(request)["email"] == "admin@example.com"
        assert _decrypt_password(request) == "admin-secret"
        return httpx.Response(200, json={"jwt": "admin-token"}, request=request)

    async with httpx.AsyncClient(
        base_url="https://qa.example",
        transport=httpx.MockTransport(handler),
    ) as client:
        session = await login_verified_account(client, slot=AccountSlot.ADMIN)

    assert session.email == "admin@example.com"
    assert session.jwt == "admin-token"


@_async_test
async def test_login_fails_before_network_when_runtime_credentials_are_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("QA_USER_EMAIL", raising=False)
    monkeypatch.delenv("QA_USER_PASSWORD", raising=False)

    async with httpx.AsyncClient(base_url="https://qa.example") as client:
        with pytest.raises(
            RuntimeError,
            match="QA_USER_EMAIL and QA_USER_PASSWORD",
        ):
            await login_verified_account(client)


@_async_test
async def test_registration_uses_rotated_resend_challenge_for_verification() -> None:
    requests: list[httpx.Request] = []
    responses = iter(
        [
            {"message": "sent", "challenge_id": "initial-challenge"},
            {"message": "resent", "challenge_id": "rotated-challenge"},
            {"jwt": "verified-token", "role": "设计师"},
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/auth/pubkey":
            return httpx.Response(
                200,
                json={"public_key": _PUBLIC_KEY_PEM},
                request=request,
            )
        if request.url.path == "/api/auth/register":
            assert _decrypt_password(request) == "operator-approved-secret"
        return httpx.Response(200, json=next(responses), request=request)

    actions: Iterator[str] = iter(["resend", "654321"])
    async with httpx.AsyncClient(
        base_url="https://qa.example",
        transport=httpx.MockTransport(handler),
    ) as client:
        jwt = await complete_registration(
            client,
            email="recipient@example.com",
            password="operator-approved-secret",
            name="Runtime QA",
            read_action=lambda: next(actions),
            prefix="/api",
        )

    assert jwt == "verified-token"
    assert [request.url.path for request in requests] == [
        "/api/auth/pubkey",
        "/api/auth/register",
        "/api/auth/register/resend",
        "/api/auth/register/verify",
    ]
    assert _json_body(requests[2]) == {
        "email": "recipient@example.com",
        "challenge_id": "initial-challenge",
    }
    assert _json_body(requests[3]) == {
        "email": "recipient@example.com",
        "challenge_id": "rotated-challenge",
        "code": "654321",
    }
