import asyncio
import base64
import binascii
import time
from decimal import Decimal
from typing import Any

import httpx

from design_hub.application.image_generation.prompt_policy import compose_image_api_prompt
from design_hub.domain.enums import ModelName
from design_hub.domain.errors import DomainError
from design_hub.domain.models import GeneratedImage, ReferenceImage
from design_hub.infrastructure.providers._openai_common import (
    raise_for_status,
    retry_sleep,
)
from design_hub.infrastructure.providers.api_key_pool import ApiKeyPool
from design_hub.ports.image_store import ImageStore, StoredImage
from design_hub.ports.model_calls import ModelCallContext, ModelCallRecorder, ModelUsage
from design_hub.ports.model_provider import (
    AbstractModelProvider,
    ProviderError,
    ProviderTimeout,
    ReferenceMode,
)


class OpenAICompatImageProvider(AbstractModelProvider):
    """对 OpenAI images 标准协议编程的中转站图像 Provider（gpt-image-2 等）。

    与具体中转站（apinebula/诗云/...）解耦，只认 base_url + api_key + model。
    有参考图 → /images/edits（图生图，主业务）；无 → /images/generations（文生图）。
    返回 b64_json 或外部 url 时统一经 ImageStore 转存。httpx.AsyncClient 可注入便于测试。
    """

    reference_mode: ReferenceMode = "bytes"  # 同步走 multipart 字节（ISSUE-0065）

    def __init__(
        self,
        *,
        name: ModelName,
        unit_cost: Decimal,
        base_url: str,
        key_pool: ApiKeyPool,
        model: str,
        image_store: ImageStore,
        recorder: ModelCallRecorder,
        input_fidelity: str = "",
        response_format: str = "",
        client: httpx.AsyncClient | None = None,
        timeout: float = 180.0,
        trust_env: bool = True,
        max_retries: int = 0,
        retry_backoff: float = 2.0,
        retry_max_sleep: float = 30.0,
        retry_max_elapsed: float = 90.0,
        required_size: tuple[int, int] | None = None,
        required_quality: str | None = None,
        required_count: int | None = None,
        max_download_bytes: int = 64 * 1024 * 1024,
    ) -> None:
        if max_download_bytes <= 0:
            raise ValueError("max_download_bytes must be positive")
        self.name = name
        self.unit_cost = unit_cost
        self._base_url = base_url.rstrip("/")
        self._key_pool = key_pool
        self._model = model
        # 出图协议增强（apinebula 文档，coordinator #1092）：空串=不发该参数（保测/CI 旧行为）。
        # input_fidelity 仅 edits 端点发（保真）；response_format 两端点发（b64 自包含返回）。
        self._input_fidelity = input_fidelity
        self._response_format = response_format
        self._image_store = image_store
        self._recorder = recorder
        self._client = client
        # One operation has an absolute wall-clock deadline. The separate retry budget only
        # decides whether another attempt may start; it must not truncate a successful request.
        self._operation_timeout = timeout
        # 瞬时错误(超时/5xx/429"系统繁忙"/限流)重试：中转站 edit 端点间歇过载（ISSUE-0007）、
        # apikey 轮换后新 key 分组并发档低致套图并发打满 429（ISSUE-0047）。
        # I/O 域允许重试；默认 0 不重试(保 dev/CI 行为)，生产装配开启。4xx 业务错不重试(fail-fast)。
        self._max_retries = max_retries
        self._retry_backoff = retry_backoff
        self._retry_max_sleep = retry_max_sleep
        # Retry eligibility budget. The operation deadline above remains authoritative for
        # active HTTP awaits.
        self._retry_max_elapsed = retry_max_elapsed
        self._required_size = required_size
        self._required_quality = required_quality
        self._required_count = required_count
        self._max_download_bytes = max_download_bytes
        # 境内中转站(apinebula/诗云)应直连，trust_env=False 绕开本机 SOCKS 梯子代理
        self._trust_env = trust_env

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
        self._validate_request(size=size, n=n)
        composed = compose_image_api_prompt(prompt, negative_prompt)
        # 模态解引用（ISSUE-0065）：同步走字节；worker 按 reference_mode 已物化 data，缺=装配错。
        ref_bytes = [self._require_bytes(r) for r in reference_images]
        size_str = f"{size[0]}x{size[1]}"
        quality = self._required_quality or quality
        start_key_index = self._key_pool.reserve()
        attempt = 0
        overall_start = time.perf_counter()
        while True:
            start = time.perf_counter()
            api_key = self._key_pool.key_for(start_key_index, attempt)
            call_id = await self._recorder.start(
                context=context,
                provider="openai_compat_image",
                model=self._model,
                attempt_no=attempt + 1,
            )
            try:
                remaining = self._remaining_operation_budget(overall_start)
                request_timeout = self._timeout_for_request(remaining)
                async with asyncio.timeout(remaining):
                    if ref_bytes:
                        response = await self._edit(
                            composed,
                            ref_bytes,
                            size_str,
                            n,
                            quality,
                            api_key=api_key,
                            timeout=request_timeout,
                        )
                    else:
                        response = await self._generate(
                            composed,
                            size_str,
                            n,
                            quality,
                            api_key=api_key,
                            timeout=request_timeout,
                        )
                raise_for_status(self.name, response)  # 4xx→DomainError；5xx/429→ProviderTimeout
            except asyncio.CancelledError:
                await self._recorder.interrupt(call_id)
                raise
            except TimeoutError:
                error: ProviderError = ProviderTimeout(f"{self.name} timeout")
            except httpx.TimeoutException:
                error = ProviderTimeout(f"{self.name} timeout")
            except httpx.HTTPError:  # 连接/传输层错误
                error = ProviderTimeout(f"{self.name} transport error")
            except ProviderTimeout as exc:  # _raise_for_status 的 5xx/429（如"系统繁忙"）
                error = exc
            except DomainError as exc:
                await self._recorder.fail(
                    call_id,
                    code="provider_rejected",
                    detail=str(exc),
                )
                raise
            else:
                try:
                    body = response.json()
                except ValueError as exc:
                    await self._recorder.fail(
                        call_id,
                        code="invalid_response",
                        detail="upstream returned invalid JSON",
                    )
                    raise ProviderError(
                        f"{self.name} returned invalid JSON"
                    ) from exc
                usage, diagnostic_code = self._usage_of(body)
                await self._recorder.succeed(
                    call_id,
                    usage=usage,
                    provider_request_id=self._request_id_of(response),
                    platform_cost=self.unit_cost * n,
                    diagnostic_code=diagnostic_code,
                )
                latency_ms = int((time.perf_counter() - start) * 1000)
                return await self._parse(
                    body,
                    seed,
                    latency_ms,
                    expected_n=n,
                    operation_started_at=overall_start,
                )
            await self._recorder.fail(
                call_id,
                code="provider_timeout",
                detail=str(error),
            )
            # 瞬时网络/服务端错误（429/超时/5xx，I/O 域）：抖动退避后重试，超上限才抛。
            # 4xx 业务错在 _raise_for_status 已抛 DomainError、不入本分支（fail-fast）。
            # 穷尽条件（ISSUE-0055 (i)）：重试次数上限 或 总重试墙钟预算耗尽——持续同错(上游持久
            # 5xx)不再干等 max_retries×退避，超墙钟即 fail-closed 上抛。
            elapsed = time.perf_counter() - overall_start
            if attempt >= self._max_retries or elapsed >= self._retry_max_elapsed:
                raise error
            attempt += 1
            # 退避不跨出墙钟预算边界（剩余预算内 sleep）
            sleep = min(
                self._retry_sleep(attempt),
                self._retry_max_elapsed - elapsed,
                self._remaining_operation_budget(overall_start),
            )
            await asyncio.sleep(sleep)
            if time.perf_counter() - overall_start >= self._retry_max_elapsed:
                raise error

    @staticmethod
    def _request_id_of(response: httpx.Response) -> str | None:
        value = response.headers.get("x-request-id") or response.headers.get(
            "request-id"
        )
        return str(value) if value else None

    @classmethod
    def _usage_of(cls, body: Any) -> tuple[ModelUsage, str | None]:
        if not isinstance(body, dict) or "usage" not in body:
            return ModelUsage(), None
        raw = body["usage"]
        if not isinstance(raw, dict):
            return ModelUsage(), "usage_invalid"
        input_details = raw.get("input_tokens_details")
        output_details = raw.get("output_tokens_details")
        if input_details is not None and not isinstance(input_details, dict):
            return ModelUsage(), "usage_invalid"
        if output_details is not None and not isinstance(output_details, dict):
            return ModelUsage(), "usage_invalid"
        input_tokens, invalid_input = cls._token_value(raw.get("input_tokens"))
        output_tokens, invalid_output = cls._token_value(raw.get("output_tokens"))
        total_tokens, invalid_total = cls._token_value(raw.get("total_tokens"))
        input_text_tokens, invalid_input_text = cls._token_value(
            input_details.get("text_tokens") if input_details else None
        )
        input_image_tokens, invalid_input_image = cls._token_value(
            input_details.get("image_tokens") if input_details else None
        )
        output_image_tokens, invalid_output_image = cls._token_value(
            output_details.get("image_tokens") if output_details else None
        )
        diagnostic = "usage_invalid" if any(
            (
                invalid_input,
                invalid_output,
                invalid_total,
                invalid_input_text,
                invalid_input_image,
                invalid_output_image,
            )
        ) else None
        return ModelUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            input_text_tokens=input_text_tokens,
            input_image_tokens=input_image_tokens,
            output_image_tokens=output_image_tokens,
        ), diagnostic

    @staticmethod
    def _token_value(value: object) -> tuple[int | None, bool]:
        if value is None:
            return None, False
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value, False
        return None, True

    def _remaining_operation_budget(self, overall_start: float) -> float:
        remaining = self._operation_timeout - (time.perf_counter() - overall_start)
        if remaining <= 0:
            raise ProviderTimeout(f"{self.name} operation timeout")
        return remaining

    def _timeout_for_request(self, remaining: float) -> httpx.Timeout:
        timeout = min(self._operation_timeout, remaining)
        return httpx.Timeout(timeout, connect=min(timeout, 15.0))

    def _validate_request(self, *, size: tuple[int, int], n: int) -> None:
        if self._required_size is not None and size != self._required_size:
            raise ValueError(f"{self.name} requires size {self._required_size}")
        if self._required_count is not None and n != self._required_count:
            raise ValueError(f"{self.name} requires n={self._required_count}")

    def _retry_sleep(self, attempt: int) -> float:
        # 退避+抖动（_openai_common 单一事实源）：并发撞 429 时错峰去相关，max_sleep 封顶。
        return retry_sleep(
            attempt, backoff=self._retry_backoff, max_sleep=self._retry_max_sleep
        )

    async def _generate(
        self,
        prompt: str,
        size: str,
        n: int,
        quality: str | None = None,
        *,
        api_key: str,
        timeout: httpx.Timeout,
    ) -> httpx.Response:
        payload: dict[str, Any] = {
            "model": self._model, "prompt": prompt, "n": n, "size": size
        }
        if quality:
            payload["quality"] = quality
        if self._response_format:  # 两端点发（input_fidelity 仅 edits，generations 不发）
            payload["response_format"] = self._response_format
        return await self._request_json(
            f"{self._base_url}/images/generations", payload, api_key=api_key, timeout=timeout
        )

    async def _edit(
        self,
        prompt: str,
        images: list[bytes],
        size: str,
        n: int,
        quality: str | None = None,
        *,
        api_key: str,
        timeout: httpx.Timeout,
    ) -> httpx.Response:
        # GPT Image 2 多参考图按中转站文档重复同名 image 字段。
        data: dict[str, Any] = {"model": self._model, "prompt": prompt, "n": n, "size": size}
        if quality:
            data["quality"] = quality
        if self._response_format:  # 自包含 b64 返回，消 url 过期变数
            data["response_format"] = self._response_format
        if self._input_fidelity:  # 仅 edits：保留产品阴影/高光/透视/文字（保真核心）
            data["input_fidelity"] = self._input_fidelity
        files = [
            ("image", (f"product_{i}.png", img, "image/png")) for i, img in enumerate(images)
        ]
        return await self._request_multipart(
            f"{self._base_url}/images/edits", data, files, api_key=api_key, timeout=timeout
        )

    async def _request_json(
        self, url: str, payload: dict[str, Any], *, api_key: str, timeout: httpx.Timeout
    ) -> httpx.Response:
        headers = {"Authorization": f"Bearer {api_key}"}
        if self._client is not None:
            return await self._client.post(
                url, json=payload, headers=headers, timeout=timeout
            )
        async with httpx.AsyncClient(
            timeout=timeout, trust_env=self._trust_env
        ) as client:
            return await client.post(url, json=payload, headers=headers)

    async def _request_multipart(
        self,
        url: str,
        data: dict[str, Any],
        files: list[tuple[str, tuple[str, bytes, str]]],
        *,
        api_key: str,
        timeout: httpx.Timeout,
    ) -> httpx.Response:
        headers = {"Authorization": f"Bearer {api_key}"}
        if self._client is not None:
            return await self._client.post(
                url, data=data, files=files, headers=headers, timeout=timeout
            )
        async with httpx.AsyncClient(
            timeout=timeout, trust_env=self._trust_env
        ) as client:
            return await client.post(url, data=data, files=files, headers=headers)

    async def _parse(
        self,
        body: Any,
        seed: int | None,
        latency_ms: int,
        *,
        expected_n: int,
        operation_started_at: float | None = None,
    ) -> list[GeneratedImage]:
        data = body.get("data") if isinstance(body, dict) else None
        if not data:
            raise ProviderError(f"{self.name} 未返回任何图片，请重试")
        if len(data) < expected_n:
            # under-deliver=真缺图才失败（ISSUE-0045 二修，文案对用户友好）
            raise ProviderError(
                f"{self.name} 出图数量不足（请求 {expected_n} 张、实得 {len(data)} 张），请重试"
            )
        # over-deliver（ISSUE-0045 二修，#735 用户实测倒逼）：中转站对 n=1 偶发多返属
        # I/O 域违约常态——取前 n 张、按 n 计费、不整单失败。既保住出图（图是好的），
        # 又堵原资损（成本=n×unit，不随实返张数放大）。一修的 len!=n 整单失败把
        # 上游 over-deliver 变成了用户侧出图失败，矫枉过正。
        data = data[:expected_n]
        base = seed if seed is not None else 0
        images: list[GeneratedImage] = []
        if operation_started_at is None:
            operation_started_at = time.perf_counter()
        for index, item in enumerate(data):
            stored = await self._resolve_stored_image(item, operation_started_at)
            images.append(
                GeneratedImage(
                    image_key=stored.key,
                    url=stored.url,
                    seed=base + index,
                    latency_ms=latency_ms,
                    cost=self.unit_cost,
                )
            )
        return images

    async def _resolve_stored_image(
        self, item: dict[str, Any], operation_started_at: float
    ) -> StoredImage:
        if "b64_json" in item:
            raw = item["b64_json"]
            if not isinstance(raw, str) or not raw:
                raise ProviderError(f"{self.name} 返回了无效 b64_json")
            try:
                data = base64.b64decode(raw, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise ProviderError(f"{self.name} 返回了无效 b64_json") from exc
            if not data:
                raise ProviderError(f"{self.name} 返回了空图片")
            return await self._image_store.save(data)

        raw_url = item.get("url")
        if not isinstance(raw_url, str) or not raw_url:
            raise ProviderError(f"{self.name} item has neither url nor b64_json")
        url = httpx.URL(raw_url)
        if url.scheme not in {"http", "https"} or not url.host:
            raise ProviderError(f"{self.name} 图片 URL 必须使用 http/https")
        response = await self._download_external_image(raw_url, operation_started_at)
        content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
        suffixes = {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/webp": ".webp",
        }
        suffix = suffixes.get(content_type)
        if suffix is None:
            raise ProviderError(f"{self.name} 返回了非图片内容")
        if not response.content:
            raise ProviderError(f"{self.name} 返回了空图片")
        if len(response.content) > self._max_download_bytes:
            raise ProviderError(f"{self.name} 返回图片过大")
        return await self._image_store.save(response.content, suffix=suffix)

    async def _download_external_image(
        self, url: str, operation_started_at: float
    ) -> httpx.Response:
        attempt = 0
        download_started_at = time.perf_counter()
        while True:
            try:
                remaining = self._remaining_operation_budget(operation_started_at)
                timeout = self._timeout_for_request(remaining)
                response = await self._get_external(url, timeout=timeout)
                raise_for_status(self.name, response)
                return response
            except (TimeoutError, httpx.TimeoutException, httpx.HTTPError):
                error: ProviderError = ProviderTimeout(f"{self.name} image download failed")
            except ProviderTimeout as exc:
                error = exc
            elapsed = time.perf_counter() - download_started_at
            if attempt >= self._max_retries or elapsed >= self._retry_max_elapsed:
                raise error
            attempt += 1
            sleep = min(
                self._retry_sleep(attempt),
                self._retry_max_elapsed - elapsed,
                self._remaining_operation_budget(operation_started_at),
            )
            await asyncio.sleep(sleep)

    async def _get_external(self, url: str, *, timeout: httpx.Timeout) -> httpx.Response:
        if self._client is not None:
            return await self._client.get(url, headers={}, timeout=timeout)
        async with httpx.AsyncClient(
            timeout=timeout,
            trust_env=self._trust_env,
            follow_redirects=True,
        ) as client:
            return await client.get(url, headers={})

    @staticmethod
    def _require_bytes(ref: ReferenceImage) -> bytes:
        # 装配契约：bytes 模态 provider 收到的 ReferenceImage 必带 data；缺=worker/模态装配错。
        if ref.data is None:
            raise ProviderError("同步 provider 收到无字节的参考图（reference_mode 装配错）")
        return ref.data
