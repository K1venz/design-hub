"""频控（安全加固 A-4）+ 安全相关纯函数 的单测。"""

import asyncio

import pytest

from design_hub.application.rate_limit import RateLimited, ThrottledCommand, UserRateLimiter
from design_hub.ports.task_queue import GenerationCommand
from design_hub.ports.upload_store import owns, upload_ns


def test_rate_window_limits_submissions() -> None:
    limiter = UserRateLimiter(max_per_minute=2, max_in_flight=99)
    limiter.acquire("u1")
    limiter.acquire("u1")
    with pytest.raises(RateLimited):
        limiter.acquire("u1")
    limiter.acquire("u2")  # 其他用户不受影响


def test_in_flight_cap_and_release() -> None:
    limiter = UserRateLimiter(max_per_minute=99, max_in_flight=2)
    limiter.acquire("u1")
    limiter.acquire("u1")
    with pytest.raises(RateLimited):
        limiter.acquire("u1")
    limiter.release("u1")
    limiter.acquire("u1")  # 归还后可再入


def test_throttled_command_releases_even_on_failure() -> None:
    limiter = UserRateLimiter(max_per_minute=99, max_in_flight=1)

    class _Boom(GenerationCommand):
        async def run(self, job_id: str) -> None:
            raise RuntimeError("boom")

    limiter.acquire("u1")
    cmd = ThrottledCommand(inner=_Boom(), limiter=limiter, user_id="u1")
    with pytest.raises(RuntimeError):
        asyncio.run(cmd.run("j1"))
    limiter.acquire("u1")  # 失败也已归还（finally）


def test_owns_is_namespace_prefixed() -> None:
    ns = upload_ns("user-7")
    assert owns(f"{ns}/abc.png", "user-7")
    assert not owns(f"{ns}/abc.png", "user-8")  # 越权
    assert not owns("abc.png", "user-7")  # 无命名空间
