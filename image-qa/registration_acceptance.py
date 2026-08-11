from __future__ import annotations

import asyncio
import getpass
import os
from collections.abc import Callable

import httpx
from qa_auth import encrypt_password


def _required(value: str, label: str) -> str:
    result = value.strip()
    if not result:
        raise RuntimeError(f"{label} is required")
    return result


def _challenge_id(response: httpx.Response) -> str:
    challenge_id = response.json().get("challenge_id")
    if not isinstance(challenge_id, str) or not challenge_id:
        raise RuntimeError("Registration response did not contain a challenge_id")
    return challenge_id


async def complete_registration(
    client: httpx.AsyncClient,
    *,
    email: str,
    password: str,
    name: str,
    read_action: Callable[[], str],
    prefix: str = "",
) -> str:
    encrypted_password = await encrypt_password(client, password, prefix=prefix)
    response = await client.post(
        f"{prefix}/auth/register",
        json={"email": email, "password": encrypted_password, "name": name},
    )
    response.raise_for_status()
    challenge_id = _challenge_id(response)

    while True:
        action = read_action().strip()
        if action.lower() == "resend":
            response = await client.post(
                f"{prefix}/auth/register/resend",
                json={"email": email, "challenge_id": challenge_id},
            )
            response.raise_for_status()
            challenge_id = _challenge_id(response)
            continue
        if len(action) != 6 or not action.isascii() or not action.isdigit():
            raise RuntimeError("Verification code must contain six ASCII digits")
        response = await client.post(
            f"{prefix}/auth/register/verify",
            json={
                "email": email,
                "challenge_id": challenge_id,
                "code": action,
            },
        )
        response.raise_for_status()
        jwt = response.json().get("jwt")
        if not isinstance(jwt, str) or not jwt:
            raise RuntimeError("Verification response did not contain a non-empty jwt")
        return jwt


def _read_action() -> str:
    return input("输入 6 位验证码，或输入 resend 重发：")


async def _main() -> None:
    base_url = _required(os.environ.get("QA_BASE", ""), "QA_BASE")
    prefix = os.environ.get("API_PREFIX", "").rstrip("/")
    email = _required(input("本次验收邮箱："), "recipient email")
    password = _required(
        getpass.getpass("本次经批准的测试密码（不回显）："),
        "approved password",
    )
    name = _required(input("本次测试账号名称："), "account name")

    async with httpx.AsyncClient(
        base_url=base_url,
        trust_env=False,
        timeout=60.0,
    ) as client:
        await complete_registration(
            client,
            email=email,
            password=password,
            name=name,
            read_action=_read_action,
            prefix=prefix,
        )
    print("注册验收成功；账号已验证可用。")


if __name__ == "__main__":
    asyncio.run(_main())
