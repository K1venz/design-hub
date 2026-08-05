import asyncio
import base64
import json
from decimal import Decimal
from io import BytesIO

import httpx
import pytest
from model_call_fakes import RecordingModelCallRecorder
from PIL import Image

from design_hub.domain.admin import ModelOperation
from design_hub.domain.image_capabilities import ImageOutputSpec
from design_hub.domain.models import ReferenceImage
from design_hub.domain.nano_banana import NANO_BANANA_2_MODEL_ID
from design_hub.domain.tasking import RenderTier
from design_hub.infrastructure.providers.api_key_pool import ApiKeyPool
from design_hub.infrastructure.providers.gemini_native import (
    GeminiNativeImageProvider,
)
from design_hub.ports.image_store import ImageStore, StoredImage
from design_hub.ports.model_calls import ModelCallContext
from design_hub.ports.model_provider import ProviderError


class _Store(ImageStore):
    def __init__(self) -> None:
        self.saved: list[tuple[bytes, str]] = []

    async def save(self, data: bytes, *, suffix: str = ".png") -> StoredImage:
        self.saved.append((data, suffix))
        return StoredImage(key=f"nano-{len(self.saved)}{suffix}", url="/images/nano")

    async def load(self, image_key: str) -> bytes:
        raise AssertionError("Gemini result storage must not load images")


def _png(color: tuple[int, int, int]) -> bytes:
    output = BytesIO()
    Image.new("RGB", (8, 8), color).save(output, format="PNG")
    return output.getvalue()


def test_generate_content_sends_native_edit_payload_and_stores_image() -> None:
    source = _png((10, 20, 30))
    result = _png((40, 50, 60))
    captured: list[tuple[str, str, dict[str, object]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(
            (
                str(request.url),
                request.headers["authorization"],
                json.loads(request.content),
            )
        )
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "inlineData": {
                                        "mimeType": "image/png",
                                        "data": base64.b64encode(result).decode(),
                                    },
                                    "thoughtSignature": "not-persisted",
                                }
                            ],
                            "role": "model",
                        },
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 27,
                    "candidatesTokenCount": 1120,
                    "totalTokenCount": 1147,
                },
                "modelVersion": "gemini-3.1-flash-image",
                "responseId": "response-1",
            },
        )

    async def run() -> None:
        store = _Store()
        recorder = RecordingModelCallRecorder()
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        provider = GeminiNativeImageProvider(
            name=NANO_BANANA_2_MODEL_ID,
            unit_cost=Decimal("0.10"),
            base_url="https://api.example.test",
            key_pool=ApiKeyPool(("key-a", "key-b")),
            model="gemini-3.1-flash-image",
            image_store=store,
            recorder=recorder,
            client=client,
            max_retries=0,
        )
        try:
            images = await provider.generate(
                context=ModelCallContext(
                    user_id="7",
                    operation=ModelOperation.IMAGE_EDIT,
                ),
                prompt="Keep the product and change the background",
                negative_prompt="",
                reference_images=[ReferenceImage(data=source)],
                output=ImageOutputSpec(
                    ratio="4:5",
                    render_tier=RenderTier.TWO_K,
                    size=(1856, 2304),
                ),
                n=1,
                seed=9,
            )
        finally:
            await client.aclose()

        assert len(images) == 1
        assert images[0].image_key == "nano-1.png"
        assert images[0].seed == 9
        assert images[0].cost == Decimal("0.10")
        assert store.saved == [(result, ".png")]
        assert recorder.succeeded[0].provider_request_id == "response-1"
        assert recorder.succeeded[0].usage.input_tokens == 27
        assert recorder.succeeded[0].usage.output_tokens == 1120
        assert recorder.succeeded[0].usage.total_tokens == 1147

    asyncio.run(run())

    assert len(captured) == 1
    url, authorization, payload = captured[0]
    assert url == (
        "https://api.example.test/v1beta/models/"
        "gemini-3.1-flash-image:generateContent"
    )
    assert authorization == "Bearer key-a"
    contents = payload["contents"]
    assert isinstance(contents, list)
    message = contents[0]
    assert isinstance(message, dict)
    parts = message["parts"]
    assert isinstance(parts, list)
    text_part = parts[0]
    assert isinstance(text_part, dict)
    assert str(text_part["text"]).endswith(
        "Keep the product and change the background"
    )
    assert parts[1] == {
        "inlineData": {
            "mimeType": "image/png",
            "data": base64.b64encode(source).decode(),
        }
    }
    assert payload["generationConfig"] == {
        "responseModalities": ["IMAGE"],
        "imageConfig": {
            "aspectRatio": "4:5",
            "imageSize": "2K",
        },
    }


def test_rate_limit_rotates_to_next_key_and_records_each_attempt() -> None:
    result = _png((70, 80, 90))
    authorizations: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        authorizations.append(request.headers["authorization"])
        if len(authorizations) == 1:
            return httpx.Response(429, text="rate limited")
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "inlineData": {
                                        "mimeType": "image/png",
                                        "data": base64.b64encode(result).decode(),
                                    }
                                }
                            ],
                            "role": "model",
                        },
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {},
                "modelVersion": "gemini-3.1-flash-image",
                "responseId": "response-2",
            },
        )

    async def run() -> None:
        store = _Store()
        recorder = RecordingModelCallRecorder()
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        provider = GeminiNativeImageProvider(
            name=NANO_BANANA_2_MODEL_ID,
            unit_cost=Decimal("0.10"),
            base_url="https://api.example.test",
            key_pool=ApiKeyPool(("key-a", "key-b")),
            model="gemini-3.1-flash-image",
            image_store=store,
            recorder=recorder,
            client=client,
            max_retries=1,
        )
        try:
            images = await provider.generate(
                context=ModelCallContext(
                    user_id="7",
                    operation=ModelOperation.IMAGE_GENERATION,
                ),
                prompt="Generate a product image",
                negative_prompt="",
                reference_images=[],
                output=ImageOutputSpec(
                    ratio="1:1",
                    render_tier=RenderTier.STANDARD,
                    size=(1024, 1024),
                ),
                n=1,
            )
        finally:
            await client.aclose()

        assert len(images) == 1
        assert [call.attempt_no for call in recorder.started] == [1, 2]
        assert recorder.failed[0].code == "provider_timeout"
        assert recorder.succeeded[0].call_id == "call-2"

    asyncio.run(run())

    assert authorizations == ["Bearer key-a", "Bearer key-b"]


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, json={"candidates": []}),
        httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "inlineData": {
                                        "mimeType": "image/png",
                                        "data": "not-base64!",
                                    }
                                }
                            ]
                        }
                    }
                ]
            },
        ),
    ],
)
def test_malformed_image_response_fails_without_storage(
    response: httpx.Response,
) -> None:
    async def run() -> None:
        store = _Store()
        client = httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _request: response)
        )
        provider = GeminiNativeImageProvider(
            name=NANO_BANANA_2_MODEL_ID,
            unit_cost=Decimal("0.10"),
            base_url="https://api.example.test",
            key_pool=ApiKeyPool(("key-a",)),
            model="gemini-3.1-flash-image",
            image_store=store,
            recorder=RecordingModelCallRecorder(),
            client=client,
        )
        try:
            with pytest.raises(ProviderError, match="invalid image response"):
                await provider.generate(
                    context=ModelCallContext(
                        user_id="7",
                        operation=ModelOperation.IMAGE_GENERATION,
                    ),
                    prompt="Generate a product image",
                    negative_prompt="",
                    reference_images=[],
                    output=ImageOutputSpec(
                        ratio="1:1",
                        render_tier=RenderTier.STANDARD,
                        size=(1024, 1024),
                    ),
                    n=1,
                )
        finally:
            await client.aclose()
        assert store.saved == []

    asyncio.run(run())


def test_rejects_output_outside_nano_banana_contract_before_network() -> None:
    async def run() -> None:
        calls = 0

        def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(500)

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        provider = GeminiNativeImageProvider(
            name=NANO_BANANA_2_MODEL_ID,
            unit_cost=Decimal("0.10"),
            base_url="https://api.example.test",
            key_pool=ApiKeyPool(("key-a",)),
            model="gemini-3.1-flash-image",
            image_store=_Store(),
            recorder=RecordingModelCallRecorder(),
            client=client,
        )
        try:
            with pytest.raises(ValueError, match="output contract"):
                await provider.generate(
                    context=ModelCallContext(
                        user_id="7",
                        operation=ModelOperation.IMAGE_GENERATION,
                    ),
                    prompt="Generate a product image",
                    negative_prompt="",
                    reference_images=[],
                    output=ImageOutputSpec(
                        ratio="4:5",
                        render_tier=RenderTier.TWO_K,
                        size=(1024, 1024),
                    ),
                    n=1,
                )
        finally:
            await client.aclose()
        assert calls == 0

    asyncio.run(run())
