import time
from decimal import Decimal
from typing import Any

import httpx

from design_hub.domain.enums import ModelName
from design_hub.domain.models import GeneratedImage
from design_hub.ports.model_provider import (
    AbstractModelProvider,
    ProviderError,
    ProviderTimeout,
)


class OpenAICompatImageProvider(AbstractModelProvider):
    """对 OpenAI images 标准协议编程的中转站图像 Provider（gpt-image-2 等）。

    与具体中转站（诗云/API易/...）解耦，只认 base_url + api_key + model；
    httpx.AsyncClient 可注入便于测试（DIP）。
    """

    def __init__(
        self,
        *,
        name: ModelName,
        unit_cost: Decimal,
        base_url: str,
        api_key: str,
        model: str,
        client: httpx.AsyncClient | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.name = name
        self.unit_cost = unit_cost
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._client = client
        self._timeout = timeout

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
        payload = {
            "model": self._model,
            "prompt": self._compose(prompt, negative_prompt),
            "n": n,
            "size": f"{size[0]}x{size[1]}",
            "response_format": "url",
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        url = f"{self._base_url}/images/generations"
        start = time.perf_counter()
        try:
            response = await self._post(url, payload, headers)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise ProviderTimeout(f"{self.name} timeout: {exc}") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"{self.name} http error: {exc}") from exc
        latency_ms = int((time.perf_counter() - start) * 1000)
        return self._parse(response.json(), seed, latency_ms)

    async def _post(
        self, url: str, payload: dict[str, Any], headers: dict[str, str]
    ) -> httpx.Response:
        if self._client is not None:
            return await self._client.post(
                url, json=payload, headers=headers, timeout=self._timeout
            )
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            return await client.post(url, json=payload, headers=headers)

    def _parse(self, body: Any, seed: int | None, latency_ms: int) -> list[GeneratedImage]:
        data = body.get("data") if isinstance(body, dict) else None
        if not data:
            raise ProviderError(f"{self.name} empty response")
        base = seed if seed is not None else 0
        images: list[GeneratedImage] = []
        for index, item in enumerate(data):
            image_url = item.get("url")
            if image_url is None:
                raise ProviderError(
                    f"{self.name} item missing url (b64 handling TBD with chosen gateway)"
                )
            images.append(
                GeneratedImage(
                    url=image_url,
                    seed=base + index,
                    latency_ms=latency_ms,
                    cost=self.unit_cost,
                )
            )
        return images

    def _compose(self, prompt: str, negative_prompt: str) -> str:
        # gpt-image 协议无 negative 字段：把负面约束并入正向文本，避免信息丢失
        if not negative_prompt:
            return prompt
        return f"{prompt}\n（请避免：{negative_prompt}）"
