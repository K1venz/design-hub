import asyncio
import base64
import binascii
import time
from decimal import Decimal
from io import BytesIO
from typing import Any

import httpx
from PIL import Image, UnidentifiedImageError

from design_hub.application.image_generation.prompt_policy import compose_image_api_prompt
from design_hub.domain.errors import DomainError
from design_hub.domain.image_capabilities import (
    ImageOutputSpec,
    image_model_capabilities,
)
from design_hub.domain.models import GeneratedImage, ReferenceImage
from design_hub.domain.nano_banana import NANO_BANANA_UPSTREAM_MODEL
from design_hub.domain.tasking import RenderTier
from design_hub.infrastructure.providers.api_key_pool import ApiKeyPool
from design_hub.ports.image_store import ImageStore
from design_hub.ports.model_calls import ModelCallContext, ModelCallRecorder, ModelUsage
from design_hub.ports.model_provider import (
    AbstractModelProvider,
    ProviderError,
    ProviderTimeout,
    ReferenceMode,
)

_IMAGE_SIZES = {
    RenderTier.STANDARD: "1K",
    RenderTier.TWO_K: "2K",
    RenderTier.FOUR_K: "4K",
}
_RESULT_SUFFIXES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}
_REFERENCE_MIME_TYPES = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "WEBP": "image/webp",
}


class GeminiNativeImageProvider(AbstractModelProvider):
    reference_mode: ReferenceMode = "bytes"

    def __init__(
        self,
        *,
        name: str,
        unit_cost: Decimal,
        base_url: str,
        key_pool: ApiKeyPool,
        model: str,
        image_store: ImageStore,
        recorder: ModelCallRecorder,
        client: httpx.AsyncClient | None = None,
        timeout: float = 300.0,
        trust_env: bool = False,
        max_retries: int = 0,
    ) -> None:
        if model != NANO_BANANA_UPSTREAM_MODEL:
            raise ValueError("unsupported Gemini image model")
        if timeout <= 0 or max_retries < 0:
            raise ValueError("invalid Gemini network settings")
        self.name = name
        self.unit_cost = unit_cost
        self._base_url = base_url.rstrip("/")
        self._key_pool = key_pool
        self._model = model
        self._image_store = image_store
        self._recorder = recorder
        self._client = client
        self._timeout = httpx.Timeout(timeout, connect=min(timeout, 15.0))
        self._trust_env = trust_env
        self._max_retries = max_retries

    async def generate(
        self,
        *,
        context: ModelCallContext,
        prompt: str,
        negative_prompt: str,
        reference_images: list[ReferenceImage],
        output: ImageOutputSpec,
        n: int,
        seed: int | None = None,
        quality: str | None = None,
    ) -> list[GeneratedImage]:
        del quality
        if n != 1:
            raise ValueError("Gemini image provider requires n=1")
        expected_output = image_model_capabilities(self.name).output_for(
            output.render_tier, output.ratio
        )
        if output != expected_output:
            raise ValueError("output does not match Nano Banana output contract")
        parts: list[dict[str, object]] = [
            {"text": compose_image_api_prompt(prompt, negative_prompt)}
        ]
        parts.extend(self._reference_part(reference) for reference in reference_images)
        payload: dict[str, object] = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "responseModalities": ["IMAGE"],
                "imageConfig": {
                    "aspectRatio": output.ratio,
                    "imageSize": _IMAGE_SIZES[output.render_tier],
                },
            },
        }
        started = time.perf_counter()
        start_key_index = self._key_pool.reserve()
        attempt = 0
        while True:
            call_id = await self._recorder.start(
                context=context,
                provider="gemini_native_image",
                model=self.name,
                attempt_no=attempt + 1,
            )
            try:
                response = await self._post(
                    payload,
                    api_key=self._key_pool.key_for(start_key_index, attempt),
                )
                self._raise_for_status(response)
                body = response.json()
                image_data, suffix = self._image_result(body)
            except asyncio.CancelledError:
                await self._recorder.interrupt(call_id)
                raise
            except (ProviderTimeout, httpx.TimeoutException, httpx.HTTPError) as exc:
                error = ProviderTimeout(f"{self.name} transport error")
                await self._recorder.fail(
                    call_id,
                    code="provider_timeout",
                    detail=str(error),
                )
                if attempt >= self._max_retries:
                    raise error from exc
                attempt += 1
                continue
            except DomainError:
                await self._recorder.fail(
                    call_id,
                    code="provider_rejected",
                    detail=f"{self.name} request rejected",
                )
                raise
            except (
                IndexError,
                KeyError,
                StopIteration,
                TypeError,
                ValueError,
                binascii.Error,
            ) as exc:
                await self._recorder.fail(
                    call_id,
                    code="invalid_response",
                    detail=f"{self.name} returned invalid image response",
                )
                raise ProviderError(
                    f"{self.name} returned invalid image response"
                ) from exc
            stored = await self._image_store.save(image_data, suffix=suffix)
            await self._recorder.succeed(
                call_id,
                usage=self._usage(body),
                provider_request_id=self._response_id(body, response),
                platform_cost=self.unit_cost,
            )
            return [
                GeneratedImage(
                    image_key=stored.key,
                    url=stored.url,
                    seed=seed or 0,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    cost=self.unit_cost,
                )
            ]

    async def _post(
        self, payload: dict[str, object], *, api_key: str
    ) -> httpx.Response:
        url = f"{self._base_url}/v1beta/models/{self._model}:generateContent"
        headers = {"Authorization": f"Bearer {api_key}"}
        if self._client is not None:
            return await self._client.post(
                url,
                headers=headers,
                json=payload,
                timeout=self._timeout,
            )
        async with httpx.AsyncClient(trust_env=self._trust_env) as client:
            return await client.post(
                url,
                headers=headers,
                json=payload,
                timeout=self._timeout,
            )

    @staticmethod
    def _reference_part(reference: ReferenceImage) -> dict[str, object]:
        if reference.data is None:
            raise ValueError("Gemini reference image bytes are required")
        try:
            with Image.open(BytesIO(reference.data)) as image:
                image_format = image.format
                image.verify()
        except (UnidentifiedImageError, OSError, SyntaxError):
            raise ValueError("invalid Gemini reference image") from None
        try:
            if image_format is None:
                raise KeyError
            mime_type = _REFERENCE_MIME_TYPES[image_format]
        except KeyError:
            raise ValueError("unsupported Gemini reference image type") from None
        return {
            "inlineData": {
                "mimeType": mime_type,
                "data": base64.b64encode(reference.data).decode(),
            }
        }

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.status_code == 429 or response.status_code >= 500:
            raise ProviderTimeout("Gemini image provider unavailable")
        if response.status_code >= 400:
            raise DomainError("Gemini image request rejected")

    @staticmethod
    def _image_result(body: Any) -> tuple[bytes, str]:
        if not isinstance(body, dict):
            raise TypeError("invalid Gemini response")
        parts = body["candidates"][0]["content"]["parts"]
        inline = next(part["inlineData"] for part in parts if "inlineData" in part)
        mime_type = inline["mimeType"]
        suffix = _RESULT_SUFFIXES[mime_type]
        data = base64.b64decode(inline["data"], validate=True)
        if not data:
            raise ValueError("empty Gemini image")
        return data, suffix

    @staticmethod
    def _usage(body: dict[str, Any]) -> ModelUsage:
        usage = body.get("usageMetadata")
        if not isinstance(usage, dict):
            return ModelUsage()
        return ModelUsage(
            input_tokens=GeminiNativeImageProvider._token(usage.get("promptTokenCount")),
            output_tokens=GeminiNativeImageProvider._token(
                usage.get("candidatesTokenCount")
            ),
            total_tokens=GeminiNativeImageProvider._token(usage.get("totalTokenCount")),
        )

    @staticmethod
    def _token(value: object) -> int | None:
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    @staticmethod
    def _response_id(body: dict[str, Any], response: httpx.Response) -> str | None:
        value = body.get("responseId") or response.headers.get("x-request-id")
        return str(value) if value else None
