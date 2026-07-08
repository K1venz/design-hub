import asyncio
import base64
import random
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
        api_keys: list[str],
        model: str,
        input_fidelity: str = "",
        response_format: str = "",
        image_store: ImageStore | None = None,
        client: httpx.AsyncClient | None = None,
        timeout: float = 180.0,
        trust_env: bool = True,
        max_retries: int = 0,
        retry_backoff: float = 2.0,
        retry_max_sleep: float = 30.0,
        retry_max_elapsed: float = 90.0,
    ) -> None:
        self.name = name
        self.unit_cost = unit_cost
        self._base_url = base_url.rstrip("/")
        if not api_keys:
            raise ValueError("api_keys 不能为空")
        self._api_keys = api_keys
        self._key_idx = 0  # 多 key round-robin 游标
        self._model = model
        # 出图协议增强（apinebula 文档，coordinator #1092）：空串=不发该参数（保测/CI 旧行为）。
        # input_fidelity 仅 edits 端点发（保真）；response_format 两端点发（b64 自包含返回）。
        self._input_fidelity = input_fidelity
        self._response_format = response_format
        self._image_store = image_store
        self._client = client
        self._timeout = timeout
        # connect 快失败(≤15s)，read/write 容忍慢响应：gpt-image 图生图 edit 实测 ~187s
        # （ISSUE-0007：edit 比文生图慢得多，单一短超时会卡在临界点误判超时）
        self._client_timeout = httpx.Timeout(timeout, connect=min(timeout, 15.0))
        # 瞬时错误(超时/5xx/429"系统繁忙"/限流)重试：中转站 edit 端点间歇过载（ISSUE-0007）、
        # apikey 轮换后新 key 分组并发档低致套图并发打满 429（ISSUE-0047）。
        # I/O 域允许重试；默认 0 不重试(保 dev/CI 行为)，生产装配开启。4xx 业务错不重试(fail-fast)。
        self._max_retries = max_retries
        self._retry_backoff = retry_backoff
        self._retry_max_sleep = retry_max_sleep
        # 总重试墙钟预算(ISSUE-0055 (i))：retry_max_sleep 只封单次退避，持续同错(上游持久
        # 5xx)仍会耗尽 max_retries×退避干等数分钟。本预算封顶整个重试窗口的墙钟——超预算即
        # 穷尽 fail-closed 落「失败」，用户短墙钟内得反馈而非干等。只 gate 重试、不砍首次/成功请求。
        self._retry_max_elapsed = retry_max_elapsed
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
        quality: str | None = None,
    ) -> list[GeneratedImage]:
        composed = self._compose(prompt, negative_prompt)
        size_str = f"{size[0]}x{size[1]}"
        attempt = 0
        overall_start = time.perf_counter()
        while True:
            start = time.perf_counter()
            try:
                if reference_images:
                    response = await self._edit(composed, reference_images, size_str, n, quality)
                else:
                    response = await self._generate(composed, size_str, n, quality)
                self._raise_for_status(response)  # 4xx→DomainError(不重试)；5xx/429→ProviderTimeout
            except httpx.TimeoutException as exc:
                error: ProviderError = ProviderTimeout(f"{self.name} timeout: {exc}")
            except httpx.HTTPError as exc:  # 连接/传输层错误
                error = ProviderTimeout(f"{self.name} transport error: {exc}")
            except ProviderTimeout as exc:  # _raise_for_status 的 5xx/429（如"系统繁忙"）
                error = exc
            else:
                latency_ms = int((time.perf_counter() - start) * 1000)
                return await self._parse(response.json(), seed, latency_ms, expected_n=n)
            # 瞬时网络/服务端错误（429/超时/5xx，I/O 域）：抖动退避后重试，超上限才抛。
            # 4xx 业务错在 _raise_for_status 已抛 DomainError、不入本分支（fail-fast）。
            # 穷尽条件（ISSUE-0055 (i)）：重试次数上限 或 总重试墙钟预算耗尽——持续同错(上游持久
            # 5xx)不再干等 max_retries×退避，超墙钟即 fail-closed 上抛。
            elapsed = time.perf_counter() - overall_start
            if attempt >= self._max_retries or elapsed >= self._retry_max_elapsed:
                raise error
            attempt += 1
            # 退避不跨出墙钟预算边界（剩余预算内 sleep）
            sleep = min(self._retry_sleep(attempt), self._retry_max_elapsed - elapsed)
            await asyncio.sleep(sleep)

    def _retry_sleep(self, attempt: int) -> float:
        # 指数退避 + equal-jitter 抖动（ISSUE-0047）：套图多路并发同时撞 429 时，若无抖动
        # 会在同一时刻齐刷刷重发、再次打满同一限流窗口；抖动把重发时刻去相关、错峰散开。
        # 退避随 attempt 指数增长给上游限流窗口恢复时间，_retry_max_sleep 封顶防失控。
        # equal jitter：下界=backoff/2 保底退避量、上界=backoff 加随机扰动。
        backoff = min(self._retry_max_sleep, self._retry_backoff * 2.0 ** (attempt - 1))
        return backoff / 2 + random.uniform(0, backoff / 2)

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

    async def _generate(
        self, prompt: str, size: str, n: int, quality: str | None = None
    ) -> httpx.Response:
        payload: dict[str, Any] = {
            "model": self._model, "prompt": prompt, "n": n, "size": size
        }
        if quality:
            payload["quality"] = quality
        if self._response_format:  # 两端点发（input_fidelity 仅 edits，generations 不发）
            payload["response_format"] = self._response_format
        return await self._request_json(f"{self._base_url}/images/generations", payload)

    async def _edit(
        self, prompt: str, images: list[bytes], size: str, n: int, quality: str | None = None
    ) -> httpx.Response:
        # gpt-image edits 多图：同名重复字段 image[]（OpenAI gpt-image-1 协议）。
        # 中转站若不支持多图，ListingGenerationService 会在上层退化为逐图调用（见 spec §6.1 风险）。
        data = {"model": self._model, "prompt": prompt, "n": str(n), "size": size}
        if quality:
            data["quality"] = quality
        if self._response_format:  # 自包含 b64 返回，消 url 过期变数
            data["response_format"] = self._response_format
        if self._input_fidelity:  # 仅 edits：保留产品阴影/高光/透视/文字（保真核心）
            data["input_fidelity"] = self._input_fidelity
        files = [
            ("image[]", (f"product_{i}.png", img, "image/png")) for i, img in enumerate(images)
        ]
        return await self._request_multipart(f"{self._base_url}/images/edits", data, files)

    def _next_key(self) -> str:
        # 多 key round-robin（asyncio 单线程，自增不跨 await，无需锁）；并发请求自动散到多 key
        key = self._api_keys[self._key_idx % len(self._api_keys)]
        self._key_idx += 1
        return key

    async def _request_json(self, url: str, payload: dict[str, Any]) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self._next_key()}"}
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
        files: list[tuple[str, tuple[str, bytes, str]]],
    ) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self._next_key()}"}
        if self._client is not None:
            return await self._client.post(
                url, data=data, files=files, headers=headers, timeout=self._client_timeout
            )
        async with httpx.AsyncClient(
            timeout=self._client_timeout, trust_env=self._trust_env
        ) as client:
            return await client.post(url, data=data, files=files, headers=headers)

    async def _parse(
        self, body: Any, seed: int | None, latency_ms: int, *, expected_n: int
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
