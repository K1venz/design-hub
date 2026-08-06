import asyncio
import base64
import json
from decimal import Decimal
from io import BytesIO
from typing import Any

import httpx
import pytest
from model_call_fakes import RecordingModelCallRecorder
from PIL import Image

from design_hub.domain.admin import ModelOperation
from design_hub.domain.image_capabilities import ImageOutputSpec
from design_hub.domain.models import ReferenceImage
from design_hub.domain.tasking import RenderTier
from design_hub.infrastructure.providers.dashscope_wan import (
    DashScopeWanImageProvider,
)
from design_hub.ports.image_store import ImageStore, StoredImage
from design_hub.ports.model_calls import ModelCallContext
from design_hub.ports.model_provider import ProviderError, ProviderTimeout
from design_hub.ports.provider_execution import ProviderRequest


class _Store(ImageStore):
    def __init__(self) -> None:
        self.saved: list[bytes] = []

    async def save(self, data: bytes, *, suffix: str = ".png") -> StoredImage:
        self.saved.append(data)
        return StoredImage(key=f"wan-{len(self.saved)}{suffix}", url="/img/wan")

    async def load(self, image_key: str) -> bytes:
        raise AssertionError("Wan result storage must not load images")


def _request(
    *,
    refs: tuple[ReferenceImage, ...] = (),
    size: tuple[int, int] = (1536, 1024),
) -> ProviderRequest:
    return ProviderRequest(
        context=ModelCallContext(
            user_id="7",
            operation=(
                ModelOperation.IMAGE_EDIT
                if refs
                else ModelOperation.IMAGE_GENERATION
            ),
            generation_item_id="item-1",
        ),
        prompt="render a neutral red product",
        reference_images=refs,
        output=ImageOutputSpec(
            ratio="3:2",
            render_tier=RenderTier.STANDARD,
            size=size,
        ),
        seed=3,
        quality=None,
    )


def _provider(
    handler: Any,
    *,
    store: _Store | None = None,
    recorder: RecordingModelCallRecorder | None = None,
    retry_count: int = 2,
    max_download_bytes: int = 1024,
) -> tuple[
    DashScopeWanImageProvider,
    httpx.AsyncClient,
    _Store,
    RecordingModelCallRecorder,
]:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    image_store = store or _Store()
    call_recorder = recorder or RecordingModelCallRecorder()
    return (
        DashScopeWanImageProvider(
            name="wan2.7-image-pro",
            unit_cost=Decimal("0.50"),
            base_url="https://dashscope.example.test",
            api_key="wan-secret",
            model="wan2.7-image-pro",
            image_store=image_store,
            recorder=call_recorder,
            watermark=False,
            client=client,
            request_timeout=1,
            poll_interval=0,
            poll_max_elapsed=1,
            retry_count=retry_count,
            retry_backoff=0,
            max_download_bytes=max_download_bytes,
        ),
        client,
        image_store,
        call_recorder,
    )


def test_submit_contract_and_restart_safe_resume_store_one_result() -> None:
    requests: list[httpx.Request] = []
    polls = iter(["PENDING", "RUNNING", "SUCCEEDED"])

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "POST":
            return httpx.Response(
                200,
                json={"output": {"task_id": "task-123"}},
            )
        if request.url.host == "result.example.test":
            return httpx.Response(
                200,
                content=b"PNGDATA",
                headers={"content-type": "image/png"},
            )
        status = next(polls)
        output: dict[str, Any] = {"task_status": status}
        if status == "SUCCEEDED":
            output["choices"] = [
                {
                    "message": {
                        "content": [
                            {
                                "type": "image",
                                "image": (
                                    "https://result.example.test/generated.png"
                                ),
                            }
                        ]
                    }
                }
            ]
        return httpx.Response(200, json={"output": output})

    provider, client, store, recorder = _provider(handler)
    request = _request(
        refs=(ReferenceImage(url="https://uploads.example.test/product.png"),)
    )

    async def run() -> None:
        task_id = await provider.submit_task(
            request, operation_id="operation-1"
        )
        assert task_id == "task-123"
        image = await provider.resume_task(task_id, request)
        assert image.image_key == "wan-1.png"
        await client.aclose()

    asyncio.run(run())

    submit = requests[0]
    assert submit.url.path == (
        "/api/v1/services/aigc/image-generation/generation"
    )
    assert submit.headers["x-dashscope-async"] == "enable"
    assert submit.headers["authorization"] == "Bearer wan-secret"
    payload = json.loads(submit.content)
    assert payload["model"] == "wan2.7-image-pro"
    content = payload["input"]["messages"][0]["content"]
    assert content[0] == {
        "image": "https://uploads.example.test/product.png"
    }
    assert content[1]["text"].startswith("【全局真实性与细节质量约束】")
    assert content[1]["text"].endswith(
        "【本次生图要求】\n\nrender a neutral red product"
    )
    assert payload["parameters"] == {
        "size": "1536*1024",
        "n": 1,
        "watermark": False,
    }
    assert [
        request.url.path
        for request in requests
        if request.method == "GET"
        and request.url.host == "dashscope.example.test"
    ] == [
        "/api/v1/tasks/task-123",
        "/api/v1/tasks/task-123",
        "/api/v1/tasks/task-123",
    ]
    assert store.saved == [b"PNGDATA"]
    assert len(recorder.started) == 1
    assert recorder.started[0].model == "wan2.7-image-pro"
    assert len(recorder.succeeded) == 1


def test_submit_sends_extreme_4k_dimensions_verbatim() -> None:
    payloads: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(json.loads(request.content))
        return httpx.Response(200, json={"output": {"task_id": "task-4k"}})

    provider, client, _store, _recorder = _provider(handler)
    request = ProviderRequest(
        context=ModelCallContext(
            user_id="7",
            operation=ModelOperation.IMAGE_GENERATION,
            generation_item_id="item-4k",
        ),
        prompt="extreme vertical poster",
        reference_images=(),
        output=ImageOutputSpec(
            ratio="1:8",
            render_tier=RenderTier.FOUR_K,
            size=(1408, 11264),
        ),
        seed=4,
        quality=None,
    )

    async def run() -> None:
        assert await provider.submit_task(request, operation_id="operation-4k") == (
            "task-4k"
        )
        await client.aclose()

    asyncio.run(run())
    assert payloads[0]["parameters"]["size"] == "1408*11264"


def test_resume_does_not_submit_again_after_worker_restart() -> None:
    methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        if request.url.host == "result.example.test":
            return httpx.Response(
                200,
                content=b"PNG",
                headers={"content-type": "image/png"},
            )
        return httpx.Response(
            200,
            json={
                "output": {
                    "task_status": "SUCCEEDED",
                    "choices": [
                        {
                            "message": {
                                "content": [
                                    {
                                        "type": "image",
                                        "image": (
                                            "https://result.example.test/out.png"
                                        ),
                                    }
                                ]
                            }
                        }
                    ],
                }
            },
        )

    provider, client, _store, recorder = _provider(handler)

    async def run() -> None:
        await provider.resume_task("persisted-task", _request())
        await client.aclose()

    asyncio.run(run())
    assert methods == ["GET", "GET"]
    assert recorder.started == []


@pytest.mark.parametrize(
    ("outcome", "expected_exception"),
    [
        (httpx.ConnectError("private transport"), ProviderTimeout),
        (httpx.Response(429, text="secret upstream body"), ProviderTimeout),
        (httpx.Response(503, text="secret upstream body"), ProviderTimeout),
    ],
)
def test_poll_transient_errors_have_bounded_retries(
    outcome: object, expected_exception: type[Exception]
) -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    provider, client, _store, _recorder = _provider(
        handler, retry_count=2
    )
    with pytest.raises(expected_exception) as caught:
        asyncio.run(provider.resume_task("task-1", _request()))
    asyncio.run(client.aclose())
    assert attempts == 3
    assert "private transport" not in str(caught.value)
    assert "secret upstream body" not in str(caught.value)


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b"not-json"),
        httpx.Response(200, json={"output": {"task_status": "MYSTERY"}}),
        httpx.Response(
            200,
            json={
                "output": {
                    "task_status": "FAILED",
                    "message": "private upstream failure",
                }
            },
        ),
    ],
)
def test_invalid_or_terminal_poll_states_fail_fast_without_upstream_details(
    response: httpx.Response,
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return response

    provider, client, _store, _recorder = _provider(handler, retry_count=5)
    with pytest.raises(ProviderError) as caught:
        asyncio.run(provider.resume_task("task-1", _request()))
    asyncio.run(client.aclose())
    assert calls == 1
    assert "private upstream failure" not in str(caught.value)


@pytest.mark.parametrize(
    "candidate",
    [
        _request(
            refs=tuple(
                ReferenceImage(url=f"https://uploads.test/{index}.png")
                for index in range(10)
            )
        ),
        _request(
            refs=(ReferenceImage(url="https://uploads.test/file.gif"),)
        ),
        _request(size=(239, 1024)),
        _request(size=(8001, 1024)),
        _request(size=(240, 2000)),
    ],
)
def test_request_validation_fails_before_network(
    candidate: ProviderRequest,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("invalid requests must fail before network I/O")

    provider, client, _store, recorder = _provider(handler)
    with pytest.raises(ValueError):
        asyncio.run(
            provider.submit_task(candidate, operation_id="operation-1")
        )
    asyncio.run(client.aclose())
    assert recorder.started == []


def test_download_rejects_oversized_or_non_image_bytes_before_storage() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "result.example.test":
            return httpx.Response(
                200,
                content=b"too-large",
                headers={"content-type": "image/png"},
            )
        return httpx.Response(
            200,
            json={
                "output": {
                    "task_status": "SUCCEEDED",
                    "choices": [
                        {
                            "message": {
                                "content": [
                                    {
                                        "type": "image",
                                        "image": (
                                            "https://result.example.test/out.png"
                                        ),
                                    }
                                ]
                            }
                        }
                    ],
                }
            },
        )

    provider, client, store, _recorder = _provider(
        handler, max_download_bytes=4
    )
    with pytest.raises(ProviderError):
        asyncio.run(provider.resume_task("task-1", _request()))
    asyncio.run(client.aclose())
    assert store.saved == []


def test_submit_accepts_validated_base64_reference_image() -> None:
    buffer = BytesIO()
    Image.new("RGB", (1024, 1024), (180, 180, 180)).save(
        buffer, format="PNG"
    )
    data_url = (
        "data:image/png;base64,"
        + base64.b64encode(buffer.getvalue()).decode()
    )
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={"output": {"task_id": "probe-task"}},
        )

    provider, client, _store, _recorder = _provider(handler)
    request = _request(refs=(ReferenceImage(url=data_url),))

    async def run() -> None:
        await provider.submit_task(request, operation_id="probe")
        await client.aclose()

    asyncio.run(run())
    assert captured["input"]["messages"][0]["content"][0] == {
        "image": data_url
    }
