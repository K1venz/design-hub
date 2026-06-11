"""频控（安全加固 A-4）+ 安全相关纯函数 的单测。"""

import asyncio

import pytest

from design_hub.domain.media import image_key_from_url
from design_hub.interface.api.throttle import RateLimited, ThrottledCommand, UserRateLimiter
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


@pytest.mark.parametrize(
    ("url", "key"),
    [
        ("/img/a1b2.png", "a1b2.png"),
        ("https://host/img/a1b2.png", "a1b2.png"),
        ("https://bucket.tos-cn-shanghai.volces.com/a1b2.png?X-Tos-Sig=xx", "a1b2.png"),
    ],
)
def test_image_key_from_url_three_forms(url: str, key: str) -> None:
    assert image_key_from_url(url) == key
