import asyncio
import base64
import time
from decimal import Decimal
from typing import Any

import httpx

from design_hub.domain.enums import ModelName
from design_hub.domain.errors import DomainError
from design_hub.domain.models import GeneratedImage
from design_hub.ports.image_store import ImageStore
from design_hub.ports.model_provider import (
    AbstractModelProvider,
    ProviderError,
    ProviderTimeout,
)


class OpenAICompatImageProvider(AbstractModelProvider):
    """对 OpenAI images 标准协议编程的中转站图像 Provider（gpt-image-2 等）。

    与具体中转站（apinebula/诗云/...）解耦，只认 base_url + api_key + model。
    有参考图 → /images/edits（图生图，主业务）；无 → /images/generations（文生图）。
    返回 b64_json 时经 ImageStore 落点换 url（DIP）。httpx.AsyncClient 可注入便于测试。
    """

    def __init__(
        self,
        *,
        name: ModelName,
        unit_cost: Decimal,
        base_url: str,
        api_key: str,
        model: str,
        image_store: ImageStore | None = None,
        client: httpx.AsyncClient | None = None,
        timeout: float = 180.0,
        trust_env: bool = True,
        max_retries: int = 0,
        retry_backoff: float = 2.0,
    ) -> None:
        self.name = name
        self.unit_cost = unit_cost
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._image_store = image_store
        self._client = client
        self._timeout = timeout
        # connect 快失败(≤15s)，read/write 容忍慢响应：gpt-image 图生图 edit 实测 ~187s
        # （ISSUE-0007：edit 比文生图慢得多，单一短超时会卡在临界点误判超时）
        self._client_timeout = httpx.Timeout(timeout, connect=min(timeout, 15.0))
        # 瞬时错误(超时/5xx/429"系统繁忙")重试：中转站 edit 端点间歇过载（ISSUE-0007）。
        # I/O 域允许重试；默认 0 不重试(保 dev/CI 行为)，生产装配开启。4xx 不重试。
        self._max_retries = max_retries
        self._retry_backoff = retry_backoff
        # 境内中转站(apinebula/诗云)应直连，trust_env=False 绕开本机 SOCKS 梯子代理
        self._trust_env = trust_env

    async def generate(
        self,
        *,
        prompt: str,
        negative_prompt: str,
        reference_images: list[bytes],
        size: tuple[int, int],
        n: int,
        seed: int | None = None,
    ) -> list[GeneratedImage]:
        composed = self._compose(prompt, negative_prompt)
        size_str = f"{size[0]}x{size[1]}"
        attempt = 0
        while True:
            start = time.perf_counter()
            try:
                if reference_images:
                    response = await self._edit(composed, reference_images[0], size_str, n)
                else:
                    response = await self._generate(composed, size_str, n)
                self._raise_for_status(response)  # 4xx→DomainError(不重试)；5xx/429→ProviderTimeout
            except httpx.TimeoutException as exc:
                error: ProviderError = ProviderTimeout(f"{self.name} timeout: {exc}")
            except httpx.HTTPError as exc:  # 连接/传输层错误
                error = ProviderTimeout(f"{self.name} transport error: {exc}")
            except ProviderTimeout as exc:  # _raise_for_status 的 5xx/429（如"系统繁忙"）
                error = exc
            else:
                latency_ms = int((time.perf_counter() - start) * 1000)
                return await self._parse(response.json(), seed, latency_ms)
            # 瞬时网络/服务端错误（I/O 域）：退避后重试，超出上限才抛
            if attempt >= self._max_retries:
                raise error
            attempt += 1
            await asyncio.sleep(self._retry_backoff * attempt)

    def _raise_for_status(self, response: httpx.Response) -> None:
        # 按 status_code 分流（不对错误体调 .json()，诗云 502 是 nginx HTML）
        code = response.status_code
        if 200 <= code < 300:
            return
        snippet = response.text[:200]
        if code == 429 or code >= 500:
            # 限流/服务端故障 → 可切同模型备用中转
            raise ProviderTimeout(f"{self.name} {code}: {snippet}")
        # 其余 4xx（400/401/403/422…）坏请求/鉴权/配置 → 上抛不切备（换网关无意义）
        raise DomainError(f"{self.name} {code} (不切备): {snippet}")

    async def _generate(self, prompt: str, size: str, n: int) -> httpx.Response:
        payload = {"model": self._model, "prompt": prompt, "n": n, "size": size}
        return await self._request_json(f"{self._base_url}/images/generations", payload)

    async def _edit(
        self, prompt: str, image: bytes, size: str, n: int
    ) -> httpx.Response:
        data = {"model": self._model, "prompt": prompt, "n": str(n), "size": size}
        files = {"image": ("product.png", image, "image/png")}
        return await self._request_multipart(f"{self._base_url}/images/edits", data, files)

    async def _request_json(self, url: str, payload: dict[str, Any]) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        if self._client is not None:
            return await self._client.post(
                url, json=payload, headers=headers, timeout=self._client_timeout
            )
        async with httpx.AsyncClient(
            timeout=self._client_timeout, trust_env=self._trust_env
        ) as client:
            return await client.post(url, json=payload, headers=headers)

    async def _request_multipart(
        self,
        url: str,
        data: dict[str, str],
        files: dict[str, tuple[str, bytes, str]],
    ) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        if self._client is not None:
            return await self._client.post(
                url, data=data, files=files, headers=headers, timeout=self._client_timeout
            )
        async with httpx.AsyncClient(
            timeout=self._client_timeout, trust_env=self._trust_env
        ) as client:
            return await client.post(url, data=data, files=files, headers=headers)

    async def _parse(
        self, body: Any, seed: int | None, latency_ms: int
    ) -> list[GeneratedImage]:
        data = body.get("data") if isinstance(body, dict) else None
        if not data:
            raise ProviderError(f"{self.name} empty response")
        base = seed if seed is not None else 0
        images: list[GeneratedImage] = []
        for index, item in enumerate(data):
            url = await self._resolve_url(item)
            images.append(
                GeneratedImage(
                    url=url,
                    seed=base + index,
                    latency_ms=latency_ms,
                    cost=self.unit_cost,
                )
            )
        return images

    async def _resolve_url(self, item: dict[str, Any]) -> str:
        if item.get("url"):
            return str(item["url"])
        b64 = item.get("b64_json")
        if b64:
            if self._image_store is None:
                raise ProviderError(f"{self.name} returned b64 but no ImageStore configured")
            return await self._image_store.save(base64.b64decode(b64))
        raise ProviderError(f"{self.name} item has neither url nor b64_json")

    def _compose(self, prompt: str, negative_prompt: str) -> str:
        # gpt-image 协议无 negative 字段：把负面约束并入正向文本，避免信息丢失
        if not negative_prompt:
            return prompt
        return f"{prompt}\n（请避免：{negative_prompt}）"
