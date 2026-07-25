"""AsyncImageTasksProvider 契约（ISSUE-0065）：submit shape / 轮询状态机 / download 落存 /
失败 fail-closed / 墙钟穷尽。用假 httpx client（POST 记 payload、GET 按 URL 路由轮询/下载）。"""

import asyncio
from decimal import Decimal
from typing import Any

import httpx
import pytest

from design_hub.domain.enums import ModelName
from design_hub.domain.models import ReferenceImage
from design_hub.infrastructure.providers.apinebula_async import AsyncImageTasksProvider
from design_hub.ports.image_store import ImageStore
from design_hub.ports.model_provider import ProviderError, ProviderTimeout


class _FakeImageStore(ImageStore):
    def __init__(self) -> None:
        self.saved: list[bytes] = []

    async def save(self, data: bytes, *, suffix: str = ".png") -> str:
        self.saved.append(data)
        return f"stored://{len(self.saved)}.png"

    async def load(self, image_key: str) -> bytes:
        raise NotImplementedError


def _submit_ok(task_id: str = "t1") -> httpx.Response:
    return httpx.Response(200, json={"task_id": task_id, "status": "queued"})


def _poll(status: str, urls: list[str] | None = None) -> httpx.Response:
    body: dict[str, Any] = {"status": status}
    if urls is not None:
        body["detail"] = {"data": [{"download_url": u} for u in urls]}
    return httpx.Response(200, json=body)


def _download(content: bytes = b"PNGBYTES") -> httpx.Response:
    return httpx.Response(200, content=content)


_CDN = "https://cdnimage.apinebula.com/a.png"


class _ScriptedClient:
    """POST→submit 响应并记 payload；GET→按 URL 路由（download_url 走下载、否则弹轮询序列）。"""

    def __init__(
        self, *, submit: httpx.Response, polls: list[httpx.Response], download: httpx.Response
    ) -> None:
        self._submit = submit
        self._polls = list(polls)
        self._download = download
        self.post_payloads: list[Any] = []
        self.get_headers: list[Any] = []

    async def post(self, url: str, **kw: Any) -> httpx.Response:
        self.post_payloads.append(kw.get("json"))
        return self._submit

    async def get(self, url: str, **kw: Any) -> httpx.Response:
        self.get_headers.append(kw.get("headers"))
        if "cdnimage" in url:
            return self._download
        return self._polls.pop(0)


class _AlwaysQueued:
    async def post(self, url: str, **kw: Any) -> httpx.Response:
        return _submit_ok()

    async def get(self, url: str, **kw: Any) -> httpx.Response:
        return _poll("queued")


def _provider(client: object, **kw: Any) -> AsyncImageTasksProvider:
    return AsyncImageTasksProvider(
        name=ModelName.GPT_IMAGE_2,
        unit_cost=Decimal("0.40"),
        base_url="https://api.example/v1",
        api_keys=["k"],
        model="gpt-image-2",
        image_store=kw.pop("image_store", _FakeImageStore()),
        input_fidelity=kw.pop("input_fidelity", "high"),
        client=client,  # type: ignore[arg-type]
        poll_interval=0.001,
        poll_max_elapsed=kw.pop("poll_max_elapsed", 5.0),
    )


async def _gen(
    provider: AsyncImageTasksProvider,
    refs: list[ReferenceImage],
    *,
    negative_prompt: str = "",
) -> list:
    return await provider.generate(
        prompt="生成红色水杯",
        negative_prompt=negative_prompt,
        reference_images=refs,
        size=(1536, 1024),
        n=1,
    )


def test_reference_mode_is_url() -> None:
    assert AsyncImageTasksProvider.reference_mode == "url"


def test_submit_shape_then_completed_downloads_and_stores() -> None:
    store = _FakeImageStore()
    client = _ScriptedClient(
        submit=_submit_ok("t1"),
        polls=[_poll("queued"), _poll("in_progress"), _poll("completed", [_CDN])],
        download=_download(),
    )
    images = asyncio.run(_gen(_provider(client, image_store=store), [ReferenceImage(url="https://sig/u1.png")]))
    assert len(images) == 1
    assert images[0].url == "stored://1.png" and images[0].cost == Decimal("0.40")
    # submit shape：现签 URL 进 images[{image_url}]、size 尊重、input_fidelity 保真
    payload = client.post_payloads[0]
    assert payload["model"] == "gpt-image-2" and payload["size"] == "1536x1024"
    assert payload["input_fidelity"] == "high"
    assert payload["images"] == [{"image_url": "https://sig/u1.png"}]
    # download 落存的是 CDN 直拉字节
    assert store.saved == [b"PNGBYTES"]
    # download GET 不带 Bearer（不泄 key 给 CDN 主机）；轮询 GET 带
    assert client.get_headers[-1] == {}  # 最后一次 GET=下载
    assert client.get_headers[0] == {"Authorization": "Bearer k"}  # 首次 GET=轮询


def test_failed_task_raises_provider_error_fail_closed() -> None:
    # MVP 不重投：failed=确定性终态，fail-closed 上抛（上游自动退款）
    client = _ScriptedClient(
        submit=_submit_ok(),
        polls=[_poll("in_progress"), _poll("failed")],
        download=_download(),
    )
    with pytest.raises(ProviderError, match="任务失败"):
        asyncio.run(_gen(_provider(client), [ReferenceImage(url="https://sig/u1.png")]))


def test_poll_wall_clock_exhausts_to_timeout() -> None:
    # 永远 queued → 墙钟穷尽 ProviderTimeout（不无限轮询）
    with pytest.raises(ProviderTimeout):
        asyncio.run(
            _gen(_provider(_AlwaysQueued(), poll_max_elapsed=0.05), [ReferenceImage(url="https://sig/u1.png")])
        )


def test_generations_omits_images_key_when_no_refs() -> None:
    client = _ScriptedClient(
        submit=_submit_ok(), polls=[_poll("completed", [_CDN])], download=_download()
    )
    asyncio.run(_gen(_provider(client), []))
    assert "images" not in client.post_payloads[0]


@pytest.mark.parametrize("refs", [[], [ReferenceImage(url="https://sig/u1.png")]])
def test_submit_payload_injects_policy_once_before_task_and_negative(
    refs: list[ReferenceImage],
) -> None:
    client = _ScriptedClient(
        submit=_submit_ok(), polls=[_poll("completed", [_CDN])], download=_download()
    )

    asyncio.run(_gen(_provider(client), refs, negative_prompt="不要水印"))

    prompt = str(client.post_payloads[0]["prompt"])
    assert prompt.count("【全局真实性与细节质量约束】") == 1
    assert prompt.count("生成红色水杯") == 1
    assert prompt.index("生成红色水杯") < prompt.index("【需要避免】")
    assert prompt.endswith("不要水印")


def test_require_url_fails_fast_on_bytes_only_ref() -> None:
    # 模态装配错：url provider 收到只带 data 的 ReferenceImage → fail-fast
    client = _ScriptedClient(
        submit=_submit_ok(), polls=[_poll("completed", [_CDN])], download=_download()
    )
    with pytest.raises(ProviderError, match="装配错"):
        asyncio.run(_gen(_provider(client), [ReferenceImage(data=b"bytes")]))
