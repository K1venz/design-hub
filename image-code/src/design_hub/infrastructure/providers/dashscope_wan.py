import asyncio
import base64
import binascii
import re
import time
from decimal import Decimal
from io import BytesIO
from typing import Any
from urllib.parse import urlsplit

import httpx
from PIL import Image, UnidentifiedImageError

from design_hub.application.image_generation.prompt_policy import (
    compose_image_api_prompt,
)
from design_hub.domain.models import GeneratedImage, ReferenceImage
from design_hub.ports.image_store import ImageStore, StoredImage
from design_hub.ports.model_calls import (
    ModelCallContext,
    ModelCallRecorder,
    ModelUsage,
)
from design_hub.ports.model_provider import (
    AbstractModelProvider,
    ProviderError,
    ProviderTimeout,
    ReferenceMode,
)
from design_hub.ports.provider_execution import ProviderRequest

_SAFE_TASK_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}")
_PENDING_STATES = frozenset({"PENDING", "RUNNING"})
_FAILURE_STATES = frozenset(
    {"FAILED", "CANCELED", "CANCELLED", "UNKNOWN"}
)
_REFERENCE_SUFFIXES = frozenset(
    {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
)
_DATA_IMAGE = re.compile(
    r"data:image/(?P<type>png|jpe?g|bmp|webp);base64,"
    r"(?P<data>[A-Za-z0-9+/=]+)",
    re.IGNORECASE,
)
_RESULT_CONTENT_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}
_MAX_REFERENCE_BYTES = 20 * 1024 * 1024


class DashScopeWanImageProvider(AbstractModelProvider):
    reference_mode: ReferenceMode = "url"

    def __init__(
        self,
        *,
        name: str,
        unit_cost: Decimal,
        base_url: str,
        api_key: str,
        model: str,
        image_store: ImageStore,
        recorder: ModelCallRecorder,
        watermark: bool = False,
        client: httpx.AsyncClient | None = None,
        request_timeout: float = 60,
        trust_env: bool = False,
        poll_interval: float = 6,
        poll_max_elapsed: float = 600,
        retry_count: int = 2,
        retry_backoff: float = 1,
        max_download_bytes: int = 64 * 1024 * 1024,
    ) -> None:
        if not name.strip() or not model.strip() or not api_key:
            raise ValueError("invalid Wan provider connection")
        if type(watermark) is not bool:
            raise ValueError("invalid Wan watermark option")
        if (
            request_timeout <= 0
            or poll_interval < 0
            or poll_max_elapsed <= 0
            or retry_count < 0
            or retry_backoff < 0
            or max_download_bytes <= 0
        ):
            raise ValueError("invalid Wan network settings")
        endpoint = urlsplit(base_url)
        if endpoint.scheme not in {"http", "https"} or not endpoint.netloc:
            raise ValueError("invalid Wan base URL")
        self.name = name.strip()
        self.unit_cost = unit_cost
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model.strip()
        self._image_store = image_store
        self._recorder = recorder
        self._watermark = watermark
        self._client = client
        self._request_timeout = httpx.Timeout(
            request_timeout,
            connect=min(request_timeout, 15),
        )
        self._trust_env = trust_env
        self._poll_interval = poll_interval
        self._poll_max_elapsed = poll_max_elapsed
        self._retry_count = retry_count
        self._retry_backoff = retry_backoff
        self._max_download_bytes = max_download_bytes

    async def generate(
        self,
        *,
        context: ModelCallContext,
        prompt: str,
        negative_prompt: str,
        reference_images: list[ReferenceImage],
        size: tuple[int, int],
        n: int,
        seed: int | None = None,
        quality: str | None = None,
    ) -> list[GeneratedImage]:
        if n != 1:
            raise ValueError("Wan requires n=1")
        request = ProviderRequest(
            context=context,
            prompt=compose_image_api_prompt(prompt, negative_prompt),
            reference_images=tuple(reference_images),
            size=size,
            seed=seed or 0,
            quality=quality,
        )
        task_id = await self.submit_task(
            request,
            operation_id="direct-generate",
            prompt_is_composed=True,
        )
        return [await self.resume_task(task_id, request)]

    async def submit_task(
        self,
        request: ProviderRequest,
        *,
        operation_id: str,
        prompt_is_composed: bool = False,
    ) -> str:
        del operation_id
        self._validate_request(request)
        prompt = (
            request.prompt
            if prompt_is_composed
            else compose_image_api_prompt(request.prompt, "")
        )
        content = [
            {"image": self._reference_url(reference)}
            for reference in request.reference_images
        ]
        content.append({"text": prompt})
        payload: dict[str, object] = {
            "model": self._model,
            "input": {
                "messages": [
                    {
                        "role": "user",
                        "content": content,
                    }
                ]
            },
            "parameters": {
                "size": f"{request.size[0]}*{request.size[1]}",
                "n": 1,
                "watermark": self._watermark,
            },
        }
        call_id = await self._recorder.start(
            context=request.context,
            provider="dashscope_wan_image",
            model=self.name,
            attempt_no=1,
        )
        try:
            response = await self._post_submit(payload)
            self._raise_submit_status(response)
            task_id = self._task_id(self._json_object(response))
        except asyncio.CancelledError:
            await self._recorder.interrupt(call_id)
            raise
        except ProviderTimeout as exc:
            await self._recorder.fail(
                call_id,
                code="provider_timeout",
                detail=str(exc),
            )
            raise
        except ProviderError as exc:
            await self._recorder.fail(
                call_id,
                code="invalid_response",
                detail=str(exc),
            )
            raise
        except httpx.HTTPError as exc:
            error = ProviderTimeout("Wan submission transport error")
            await self._recorder.fail(
                call_id,
                code="provider_timeout",
                detail=str(error),
            )
            raise error from exc
        await self._recorder.succeed(
            call_id,
            usage=ModelUsage(),
            provider_request_id=task_id,
            platform_cost=self.unit_cost,
        )
        return task_id

    async def resume_task(
        self,
        provider_task_id: str,
        request: ProviderRequest,
    ) -> GeneratedImage:
        if _SAFE_TASK_ID.fullmatch(provider_task_id) is None:
            raise ProviderError("invalid persisted Wan task ID")
        self._validate_request(request)
        started_at = time.monotonic()
        result_url = await self._poll_until_complete(
            provider_task_id,
            started_at=started_at,
        )
        stored = await self._download_and_store(result_url)
        return GeneratedImage(
            image_key=stored.key,
            url=stored.url,
            seed=request.seed,
            latency_ms=max(
                int((time.monotonic() - started_at) * 1000),
                0,
            ),
            cost=self.unit_cost,
        )

    async def _poll_until_complete(
        self,
        task_id: str,
        *,
        started_at: float,
    ) -> str:
        url = f"{self._base_url}/api/v1/tasks/{task_id}"
        while True:
            if time.monotonic() - started_at >= self._poll_max_elapsed:
                raise ProviderTimeout("Wan polling time budget exhausted")
            response = await self._get_with_retries(
                url,
                authorization=True,
                operation="polling",
            )
            body = self._json_object(response)
            output = body.get("output")
            if not isinstance(output, dict):
                raise ProviderError("Wan polling response is invalid")
            status = output.get("task_status")
            if status in _PENDING_STATES:
                await asyncio.sleep(self._poll_interval)
                continue
            if status in _FAILURE_STATES:
                raise ProviderError("Wan task failed")
            if status != "SUCCEEDED":
                raise ProviderError("Wan task state is invalid")
            image_urls = self._result_image_urls(output)
            if len(image_urls) != 1:
                raise ProviderError(
                    "Wan task must return exactly one image"
                )
            result_url = image_urls[0]
            parsed = urlsplit(result_url)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.netloc
            ):
                raise ProviderError("Wan task result is invalid")
            return result_url

    @staticmethod
    def _result_image_urls(output: dict[str, Any]) -> list[str]:
        choices = output.get("choices")
        if not isinstance(choices, list):
            raise ProviderError("Wan task result is invalid")
        image_urls: list[str] = []
        for choice in choices:
            message = (
                choice.get("message")
                if isinstance(choice, dict)
                else None
            )
            content = (
                message.get("content")
                if isinstance(message, dict)
                else None
            )
            if not isinstance(content, list):
                raise ProviderError("Wan task result is invalid")
            for item in content:
                if (
                    isinstance(item, dict)
                    and item.get("type") == "image"
                    and isinstance(item.get("image"), str)
                ):
                    image_urls.append(item["image"])
        return image_urls

    async def _download_and_store(self, result_url: str) -> StoredImage:
        response = await self._get_with_retries(
            result_url,
            authorization=False,
            operation="download",
        )
        content_type = (
            response.headers.get("content-type", "")
            .split(";", 1)[0]
            .lower()
        )
        suffix = _RESULT_CONTENT_TYPES.get(content_type)
        if suffix is None:
            raise ProviderError("Wan result is not a supported image")
        content_length = response.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > self._max_download_bytes:
                    raise ProviderError("Wan result image is too large")
            except ValueError as exc:
                raise ProviderError(
                    "Wan result content length is invalid"
                ) from exc
        if (
            not response.content
            or len(response.content) > self._max_download_bytes
        ):
            raise ProviderError("Wan result image is empty or too large")
        return await self._image_store.save(response.content, suffix=suffix)

    async def _get_with_retries(
        self,
        url: str,
        *,
        authorization: bool,
        operation: str,
    ) -> httpx.Response:
        for attempt in range(self._retry_count + 1):
            try:
                response = await self._get(
                    url,
                    authorization=authorization,
                )
            except (httpx.TimeoutException, httpx.TransportError):
                response = None
            if response is not None:
                if 200 <= response.status_code < 300:
                    return response
                if (
                    response.status_code != 429
                    and response.status_code < 500
                ):
                    raise ProviderError(f"Wan {operation} request rejected")
            if attempt == self._retry_count:
                raise ProviderTimeout(
                    f"Wan {operation} retry budget exhausted"
                )
            await asyncio.sleep(
                self._retry_backoff * (2**attempt)
            )
        raise AssertionError("unreachable")

    async def _post_submit(
        self, payload: dict[str, object]
    ) -> httpx.Response:
        url = (
            f"{self._base_url}"
            "/api/v1/services/aigc/image-generation/generation"
        )
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "X-DashScope-Async": "enable",
            "Content-Type": "application/json",
        }
        if self._client is not None:
            return await self._client.post(
                url,
                json=payload,
                headers=headers,
                timeout=self._request_timeout,
            )
        async with httpx.AsyncClient(
            timeout=self._request_timeout,
            trust_env=self._trust_env,
        ) as client:
            return await client.post(url, json=payload, headers=headers)

    async def _get(
        self,
        url: str,
        *,
        authorization: bool,
    ) -> httpx.Response:
        headers = (
            {"Authorization": f"Bearer {self._api_key}"}
            if authorization
            else {}
        )
        if self._client is not None:
            return await self._client.get(
                url,
                headers=headers,
                timeout=self._request_timeout,
            )
        async with httpx.AsyncClient(
            timeout=self._request_timeout,
            trust_env=self._trust_env,
            follow_redirects=not authorization,
        ) as client:
            return await client.get(url, headers=headers)

    @staticmethod
    def _raise_submit_status(response: httpx.Response) -> None:
        if 200 <= response.status_code < 300:
            return
        if response.status_code == 429 or response.status_code >= 500:
            raise ProviderTimeout("Wan submission temporarily unavailable")
        raise ProviderError("Wan submission rejected")

    @staticmethod
    def _json_object(response: httpx.Response) -> dict[str, Any]:
        try:
            body = response.json()
        except ValueError as exc:
            raise ProviderError("Wan returned invalid JSON") from exc
        if not isinstance(body, dict):
            raise ProviderError("Wan returned invalid JSON")
        return body

    @staticmethod
    def _task_id(body: dict[str, Any]) -> str:
        output = body.get("output")
        task_id = output.get("task_id") if isinstance(output, dict) else None
        if (
            not isinstance(task_id, str)
            or _SAFE_TASK_ID.fullmatch(task_id) is None
        ):
            raise ProviderError("Wan submission returned no valid task ID")
        return task_id

    @classmethod
    def _validate_request(cls, request: ProviderRequest) -> None:
        width, height = request.size
        if (
            width < 240
            or width > 8000
            or height < 240
            or height > 8000
        ):
            raise ValueError("Wan dimensions must be 240..8000")
        ratio = width / height
        if ratio < 1 / 8 or ratio > 8:
            raise ValueError("Wan aspect ratio must be within 1:8..8:1")
        if len(request.reference_images) > 9:
            raise ValueError("Wan accepts at most 9 reference images")
        for reference in request.reference_images:
            cls._reference_url(reference)
            if (
                reference.data is not None
                and len(reference.data) > _MAX_REFERENCE_BYTES
            ):
                raise ValueError(
                    "Wan reference image exceeds 20 MB"
                )

    @staticmethod
    def _reference_url(reference: ReferenceImage) -> str:
        if not reference.url:
            raise ValueError("Wan reference image URL is required")
        data_match = _DATA_IMAGE.fullmatch(reference.url)
        if data_match is not None:
            try:
                data = base64.b64decode(
                    data_match.group("data"),
                    validate=True,
                )
            except (binascii.Error, ValueError) as exc:
                raise ValueError(
                    "Wan reference image data is invalid"
                ) from exc
            DashScopeWanImageProvider._validate_reference_bytes(data)
            return reference.url
        parsed = urlsplit(reference.url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Wan reference image URL is invalid")
        path = parsed.path.lower()
        if not any(path.endswith(suffix) for suffix in _REFERENCE_SUFFIXES):
            raise ValueError("Wan reference image type is unsupported")
        return reference.url

    @staticmethod
    def _validate_reference_bytes(data: bytes) -> None:
        if not data or len(data) > _MAX_REFERENCE_BYTES:
            raise ValueError("Wan reference image exceeds 20 MB")
        try:
            with Image.open(BytesIO(data)) as image:
                if image.format not in {
                    "PNG",
                    "JPEG",
                    "BMP",
                    "WEBP",
                }:
                    raise ValueError(
                        "Wan reference image type is unsupported"
                    )
                width, height = image.size
                if (
                    width < 240
                    or width > 8000
                    or height < 240
                    or height > 8000
                    or width / height < 1 / 8
                    or width / height > 8
                ):
                    raise ValueError(
                        "Wan reference image dimensions are invalid"
                    )
                if image.mode in {"LA", "PA", "RGBA"}:
                    raise ValueError(
                        "Wan reference image alpha is unsupported"
                    )
                image.verify()
        except (UnidentifiedImageError, OSError) as exc:
            raise ValueError(
                "Wan reference image data is invalid"
            ) from exc
