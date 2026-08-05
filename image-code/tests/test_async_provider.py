"""AsyncImageTasksProvider 契约（ISSUE-0065）：submit shape / 轮询状态机 / download 落存 /
失败 fail-closed / 墙钟穷尽。用假 httpx client（POST 记 payload、GET 按 URL 路由轮询/下载）。"""

import asyncio
from decimal import Decimal
from typing import Any

import httpx
import pytest
from model_call_fakes import RecordingModelCallRecorder

from design_hub.domain.admin import ModelOperation
from design_hub.domain.image_capabilities import ImageOutputSpec
from design_hub.domain.models import ReferenceImage
from design_hub.domain.tasking import RenderTier
from design_hub.infrastructure.providers.api_key_pool import ApiKeyPool
from design_hub.infrastructure.providers.apinebula_async import AsyncImageTasksProvider
from design_hub.infrastructure.providers.openai_compat import OpenAICompatImageProvider
from design_hub.ports.image_store import ImageStore, StoredImage
from design_hub.ports.model_calls import ModelCallContext
from design_hub.ports.model_provider import ProviderError, ProviderTimeout
from design_hub.ports.provider_execution import ProviderRequest


class _FakeImageStore(ImageStore):
    def __init__(self) -> None:
        self.saved: list[bytes] = []

    async def save(self, data: bytes, *, suffix: str = ".png") -> StoredImage:
        self.saved.append(data)
        key = f"{len(self.saved)}.png"
        return StoredImage(key=key, url=f"stored://{key}")

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
        self,
        *,
        submit: httpx.Response | list[httpx.Response],
        polls: list[object],
        download: httpx.Response,
    ) -> None:
        self._submit = list(submit) if isinstance(submit, list) else [submit]
        self._polls = list(polls)
        self._download = download
        self.post_payloads: list[Any] = []
        self.post_headers: list[dict[str, str]] = []
        self.get_headers: list[Any] = []
        self.get_urls: list[str] = []

    async def post(self, url: str, **kw: Any) -> httpx.Response:
        self.post_payloads.append(kw.get("json"))
        self.post_headers.append(kw.get("headers", {}))
        return self._submit.pop(0)

    async def get(self, url: str, **kw: Any) -> httpx.Response:
        self.get_urls.append(url)
        self.get_headers.append(kw.get("headers"))
        if "cdnimage" in url:
            return self._download
        outcome = self._polls.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        assert isinstance(outcome, httpx.Response)
        return outcome


class _AlwaysQueued:
    async def post(self, url: str, **kw: Any) -> httpx.Response:
        return _submit_ok()

    async def get(self, url: str, **kw: Any) -> httpx.Response:
        return _poll("queued")


def _provider(client: object, **kw: Any) -> AsyncImageTasksProvider:
    return AsyncImageTasksProvider(
        name="gpt-image-2",
        unit_cost=Decimal("0.40"),
        base_url="https://api.example/v1",
        key_pool=kw.pop("key_pool", ApiKeyPool(("k",))),
        model="gpt-image-2",
        image_store=kw.pop("image_store", _FakeImageStore()),
        recorder=kw.pop("recorder", RecordingModelCallRecorder()),
        input_fidelity=kw.pop("input_fidelity", "high"),
        client=client,  # type: ignore[arg-type]
        poll_interval=0.001,
        poll_max_elapsed=kw.pop("poll_max_elapsed", 5.0),
        submit_max_retries=kw.pop("submit_max_retries", 0),
        submit_backoff=kw.pop("submit_backoff", 0.0),
        submit_max_sleep=kw.pop("submit_max_sleep", 0.0),
    )


async def _gen(
    provider: AsyncImageTasksProvider,
    refs: list[ReferenceImage],
    *,
    negative_prompt: str = "",
) -> list:
    return await provider.generate(
        context=ModelCallContext(
            user_id="7",
            operation=(
                ModelOperation.IMAGE_EDIT
                if refs
                else ModelOperation.IMAGE_GENERATION
            ),
        ),
        prompt="生成红色水杯",
        negative_prompt=negative_prompt,
        reference_images=refs,
        output=ImageOutputSpec(
            ratio="3:2",
            render_tier=RenderTier.STANDARD,
            size=(1536, 1024),
        ),
        n=1,
    )


def test_reference_mode_is_url() -> None:
    assert AsyncImageTasksProvider.reference_mode == "url"


def test_submit_task_returns_id_before_poll_and_resume_never_resubmits() -> None:
    client = _ScriptedClient(
        submit=_submit_ok("persist-me"),
        polls=[_poll("completed", [_CDN])],
        download=_download(),
    )
    recorder = RecordingModelCallRecorder()
    provider = _provider(client, recorder=recorder)
    request = ProviderRequest(
        context=ModelCallContext(
            user_id="7",
            operation=ModelOperation.IMAGE_EDIT,
        ),
        prompt="生成红色水杯",
        reference_images=(ReferenceImage(url="https://sig/u1.png"),),
        output=ImageOutputSpec(
            ratio="3:2",
            render_tier=RenderTier.STANDARD,
            size=(1536, 1024),
        ),
        seed=0,
        quality=None,
    )

    async def run() -> None:
        task_id = await provider.submit_task(request, operation_id="operation-1")
        assert task_id == "persist-me"
        assert client.get_urls == []
        image = await provider.resume_task(task_id, request)
        assert image.image_key == "1.png"

    asyncio.run(run())

    assert len(client.post_payloads) == 1
    assert "operation_id" not in client.post_payloads[0]
    assert [call.attempt_no for call in recorder.started] == [1]
    assert [call.call_id for call in recorder.succeeded] == ["call-1"]


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


def test_submit_without_task_id_does_not_expose_upstream_secret() -> None:
    secret = "upstream-echoed-authorization"
    client = _ScriptedClient(
        submit=httpx.Response(200, json={"authorization": f"Bearer {secret}"}),
        polls=[],
        download=_download(),
    )

    with pytest.raises(ProviderError) as error:
        asyncio.run(_gen(_provider(client), []))

    assert secret not in str(error.value)


def test_failed_task_error_message_does_not_expose_upstream_secret() -> None:
    secret = "upstream-echoed-authorization"
    client = _ScriptedClient(
        submit=_submit_ok(),
        polls=[httpx.Response(200, json={"status": "failed", "error": {"message": secret}})],
        download=_download(),
    )

    with pytest.raises(ProviderError) as error:
        asyncio.run(_gen(_provider(client), []))

    assert secret not in str(error.value)


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


def test_shared_pool_assigns_first_requests_to_different_providers() -> None:
    """若 Provider 仍维护独立游标，两次首发都会使用 key-a。"""
    pool = ApiKeyPool(("key-a", "key-b"))
    normal_client = _NormalSuccessClient()
    task_client = _ScriptedClient(
        submit=_submit_ok(), polls=[_poll("completed", [_CDN])], download=_download()
    )
    normal = OpenAICompatImageProvider(
        name="gpt-image-2",
        unit_cost=Decimal("0.40"),
        base_url="https://api.example/v1",
        key_pool=pool,
        model="gpt-image-2",
        image_store=_FakeImageStore(),
        recorder=RecordingModelCallRecorder(),
        client=normal_client,  # type: ignore[arg-type]
    )
    tasks = _provider(task_client, key_pool=pool)

    async def run() -> None:
        await normal.generate(
            context=ModelCallContext(
                user_id="7",
                operation=ModelOperation.IMAGE_GENERATION,
            ),
            prompt="normal request",
            negative_prompt="",
            reference_images=[],
            output=ImageOutputSpec(
                ratio="1:1",
                render_tier=RenderTier.STANDARD,
                size=(1024, 1024),
            ),
            n=1,
        )
        await _gen(tasks, [])

    asyncio.run(run())

    assert normal_client.headers == [{"Authorization": "Bearer key-a"}]
    assert task_client.post_headers == [{"Authorization": "Bearer key-b"}]
    assert task_client.get_headers == [
        {"Authorization": "Bearer key-b"},
        {},
    ]


def test_submit_retry_successful_key_becomes_poll_start_without_advancing_pool() -> None:
    """submit A 失败、B 成功后，轮询必须从 B 开始，且不推进共享全局游标。"""
    pool = ApiKeyPool(("key-a", "key-b"))
    client = _ScriptedClient(
        submit=[httpx.Response(429, text="busy"), _submit_ok()],
        polls=[_poll("completed", [_CDN])],
        download=_download(),
    )
    provider = _provider(
        client,
        key_pool=pool,
        submit_max_retries=1,
    )

    asyncio.run(_gen(provider, []))

    assert client.post_headers == [
        {"Authorization": "Bearer key-a"},
        {"Authorization": "Bearer key-b"},
    ]
    assert client.get_headers == [
        {"Authorization": "Bearer key-b"},
        {},
    ]
    next_request = pool.reserve()
    assert pool.key_for(next_request, 0) == "key-b"


@pytest.mark.parametrize(
    "retryable",
    [httpx.Response(500, text="busy"), httpx.ConnectError("transport")],
    ids=["server-error", "transport-error"],
)
def test_poll_retry_rotates_only_local_key_offset(retryable: object) -> None:
    pool = ApiKeyPool(("key-a", "key-b", "key-c"))
    client = _ScriptedClient(
        submit=_submit_ok(),
        polls=[retryable, _poll("completed", [_CDN])],
        download=_download(),
    )

    asyncio.run(_gen(_provider(client, key_pool=pool), []))

    assert client.post_headers == [{"Authorization": "Bearer key-a"}]
    assert client.get_headers == [
        {"Authorization": "Bearer key-a"},
        {"Authorization": "Bearer key-b"},
        {},
    ]
    next_request = pool.reserve()
    assert pool.key_for(next_request, 0) == "key-b"


def test_rejects_unsafe_task_id_without_using_or_exposing_it() -> None:
    unsafe_task_id = "../private-upstream-task"
    client = _ScriptedClient(
        submit=_submit_ok(unsafe_task_id),
        polls=[],
        download=_download(),
    )

    with pytest.raises(ProviderError) as error:
        asyncio.run(_gen(_provider(client), []))

    assert unsafe_task_id not in str(error.value)
    assert client.get_urls == []


def test_poll_timeout_does_not_expose_valid_upstream_task_id() -> None:
    task_id = "private-task-token"

    class _AlwaysQueuedTask:
        async def post(self, url: str, **kw: Any) -> httpx.Response:
            return _submit_ok(task_id)

        async def get(self, url: str, **kw: Any) -> httpx.Response:
            return _poll("queued")

    with pytest.raises(ProviderTimeout) as error:
        asyncio.run(
            _gen(_provider(_AlwaysQueuedTask(), poll_max_elapsed=0.01), [])
        )

    assert task_id not in str(error.value)


class _NormalSuccessClient:
    def __init__(self) -> None:
        self.headers: list[dict[str, str]] = []

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        self.headers.append(kwargs["headers"])
        return httpx.Response(200, json={"data": [{"b64_json": "UE5H"}]})


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
