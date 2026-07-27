"""apinebula 异步任务出图 Provider（ISSUE-0065）：submit → 轮询 → download_url 拉图落存。

同步端点在新 key 分组下过载即拒（prod 真实用户成功率 ~33%）；异步任务端点排队消化、
失败自动退款、实测零「临时繁忙」。参考图收现签公网 URL（apinebula worker 回拉，故
reference_mode="url"）；完成体的 download_url 为公网 CDN，直拉字节经 ImageStore 落存。

契约（coordinator #1107 文档+实证核对）：
- submit  POST {base}/image-tasks/{edits|generations}，JSON {model, prompt, size, quality?,
  input_fidelity?, images:[{image_url}]}，Bearer；响应 {task_id, status:"queued"}。
- 轮询    GET  {base}/image-tasks/{task_id}?detail=true → status
  queued/in_progress/completed/failed。
- 完成体  detail.data[].download_url；失败体 error.message；失败/取消上游按预扣退款。
"""

import asyncio
import re
import time
from decimal import Decimal
from typing import Any

import httpx

from design_hub.application.image_generation.prompt_policy import compose_image_api_prompt
from design_hub.domain.enums import ModelName
from design_hub.domain.models import GeneratedImage, ReferenceImage
from design_hub.infrastructure.providers._openai_common import (
    raise_for_status,
    retry_sleep,
)
from design_hub.infrastructure.providers.api_key_pool import ApiKeyPool
from design_hub.ports.image_store import ImageStore, StoredImage
from design_hub.ports.model_provider import (
    AbstractModelProvider,
    ProviderError,
    ProviderTimeout,
    ReferenceMode,
)

_STATUS_OK = "completed"
_STATUS_FAIL = "failed"
_SAFE_TASK_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}")


class AsyncImageTasksProvider(AbstractModelProvider):
    """异步任务端点适配器。与同步 provider 同占 registry GPT_IMAGE_2 槽（0057 切换=备用渠道）。"""

    reference_mode: ReferenceMode = "url"  # 参考图传现签公网 URL（worker 回拉），非字节

    def __init__(
        self,
        *,
        name: ModelName,
        unit_cost: Decimal,
        base_url: str,
        key_pool: ApiKeyPool,
        model: str,
        image_store: ImageStore,
        input_fidelity: str = "",
        client: httpx.AsyncClient | None = None,
        request_timeout: float = 60.0,
        trust_env: bool = True,
        poll_interval: float = 6.0,
        poll_max_elapsed: float = 300.0,
        submit_max_retries: int = 0,
        submit_backoff: float = 2.0,
        submit_max_sleep: float = 30.0,
    ) -> None:
        self.name = name
        self.unit_cost = unit_cost
        self._base_url = base_url.rstrip("/")
        self._key_pool = key_pool
        self._model = model
        # 异步端点只回 download_url，必须有 image_store 拉回字节落存（对齐同步 b64 落点）
        self._image_store = image_store
        self._input_fidelity = input_fidelity
        self._client = client
        self._request_timeout = httpx.Timeout(request_timeout, connect=min(request_timeout, 15.0))
        self._trust_env = trust_env
        # 轮询节奏 + 总墙钟（沿 ISSUE-0055 (i) 语义）：超墙钟=穷尽 fail-closed，用户短时得反馈。
        # 异步队列可能比同步 90s 更长，故独立更宽的默认（settings 可覆盖）。
        self._poll_interval = poll_interval
        self._poll_max_elapsed = poll_max_elapsed
        # submit 段瞬时错（429/5xx/超时）抖动退避重试；queued 后进轮询、不算错。
        self._submit_max_retries = submit_max_retries
        self._submit_backoff = submit_backoff
        self._submit_max_sleep = submit_max_sleep

    async def generate(
        self,
        *,
        prompt: str,
        negative_prompt: str,
        reference_images: list[ReferenceImage],
        size: tuple[int, int],
        n: int,
        seed: int | None = None,
        quality: str | None = None,
    ) -> list[GeneratedImage]:
        composed = compose_image_api_prompt(prompt, negative_prompt)
        # 模态解引用（ISSUE-0065）：异步走现签 URL；launcher 按 reference_mode 物化 url，缺=装配错。
        image_urls = [self._require_url(r) for r in reference_images]
        size_str = f"{size[0]}x{size[1]}"
        start = time.perf_counter()
        start_key_index = self._key_pool.reserve()
        task_id, successful_key_offset = await self._submit(
            composed, image_urls, size_str, quality, start_key_index=start_key_index
        )
        body = await self._poll(
            task_id,
            start,
            start_key_index=start_key_index,
            start_key_offset=successful_key_offset,
        )
        latency_ms = int((time.perf_counter() - start) * 1000)
        return await self._parse(body, seed, latency_ms, expected_n=n)

    async def _submit(
        self,
        prompt: str,
        image_urls: list[str],
        size: str,
        quality: str | None,
        *,
        start_key_index: int,
    ) -> tuple[str, int]:
        endpoint = "edits" if image_urls else "generations"
        payload: dict[str, Any] = {"model": self._model, "prompt": prompt, "size": size}
        if quality:
            payload["quality"] = quality
        if self._input_fidelity:
            payload["input_fidelity"] = self._input_fidelity
        if image_urls:
            payload["images"] = [{"image_url": u} for u in image_urls]
        url = f"{self._base_url}/image-tasks/{endpoint}"
        attempt = 0
        overall_start = time.perf_counter()
        while True:
            try:
                api_key = self._key_pool.key_for(start_key_index, attempt)
                response = await self._post_json(url, payload, api_key=api_key)
                raise_for_status(self.name, response)  # 4xx→DomainError；429/5xx→ProviderTimeout
            except httpx.TimeoutException:
                error: ProviderError = ProviderTimeout(f"{self.name} submit timeout")
            except httpx.HTTPError:
                error = ProviderTimeout(f"{self.name} submit transport error")
            except ProviderTimeout as exc:
                error = exc
            else:
                task_id = self._task_id_of(response.json())
                return task_id, attempt
            # submit 段瞬时错重试（I/O 域）；4xx 已在 raise_for_status 抛 DomainError 不入此分支
            elapsed = time.perf_counter() - overall_start
            if attempt >= self._submit_max_retries or elapsed >= self._poll_max_elapsed:
                raise error
            attempt += 1
            backoff = retry_sleep(
                attempt, backoff=self._submit_backoff, max_sleep=self._submit_max_sleep
            )
            await asyncio.sleep(min(backoff, self._poll_max_elapsed - elapsed))

    def _task_id_of(self, body: Any) -> str:
        task_id = body.get("task_id") or body.get("id") if isinstance(body, dict) else None
        if not isinstance(task_id, str) or _SAFE_TASK_ID.fullmatch(task_id) is None:
            raise ProviderError(f"{self.name} submit 未返回有效 task_id")
        return task_id

    async def _poll(
        self,
        task_id: str,
        start: float,
        *,
        start_key_index: int,
        start_key_offset: int,
    ) -> Any:
        url = f"{self._base_url}/image-tasks/{task_id}?detail=true"
        key_offset = start_key_offset
        while True:
            if time.perf_counter() - start >= self._poll_max_elapsed:
                # 墙钟穷尽 fail-closed（ISSUE-0055 (i)）：不无限轮询，用户短时得反馈
                raise ProviderTimeout(
                    f"{self.name} 任务轮询超墙钟 {self._poll_max_elapsed}s"
                )
            await asyncio.sleep(self._poll_interval)
            try:
                response = await self._get(
                    url,
                    api_key=self._key_pool.key_for(start_key_index, key_offset),
                )
                raise_for_status(self.name, response)
            except (httpx.HTTPError, ProviderTimeout):
                key_offset += 1
                continue  # 轮询期瞬时错（429/5xx/超时/传输）→ 墙钟内继续轮询，不炸任务
            body = response.json()
            status = body.get("status") if isinstance(body, dict) else None
            if status == _STATUS_OK:
                return body
            if status == _STATUS_FAIL:
                # MVP 不重投（coordinator 拍②）：failed=确定性终态，fail-closed 上抛，上游自动退款
                raise ProviderError(f"{self.name} 任务失败")
            # queued / in_progress（及其它非终态）→ 继续轮询

    async def _parse(
        self, body: Any, seed: int | None, latency_ms: int, *, expected_n: int
    ) -> list[GeneratedImage]:
        detail = body.get("detail") if isinstance(body, dict) else None
        data = detail.get("data") if isinstance(detail, dict) else None
        if not data:
            raise ProviderError(f"{self.name} 完成体无图片数据，请重试")
        if len(data) < expected_n:
            raise ProviderError(
                f"{self.name} 出图数量不足（请求 {expected_n} 张、实得 {len(data)} 张），请重试"
            )
        # over-deliver 截断口径同同步（ISSUE-0045）：取前 n 张、按 n 计费，不随实返放大
        data = data[:expected_n]
        base = seed if seed is not None else 0
        images: list[GeneratedImage] = []
        for index, item in enumerate(data):
            stored = await self._download_and_store(item)
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

    async def _download_and_store(self, item: dict[str, Any]) -> StoredImage:
        download_url = item.get("download_url")
        if not download_url:
            raise ProviderError(f"{self.name} 完成项缺 download_url")
        # 公网 CDN（cdnimage.apinebula.com）直拉，不带 Bearer（避免把 key 泄给 CDN 主机）
        response = await self._get(str(download_url))
        raise_for_status(self.name, response)
        return await self._image_store.save(response.content)

    @staticmethod
    def _require_url(ref: ReferenceImage) -> str:
        # 装配契约：url 模态 provider 收到的 ReferenceImage 必带 url；缺=launcher/模态装配错。
        if not ref.url:
            raise ProviderError("异步 provider 收到无 URL 的参考图（reference_mode 装配错）")
        return ref.url

    async def _post_json(
        self, url: str, payload: dict[str, Any], *, api_key: str
    ) -> httpx.Response:
        headers = {"Authorization": f"Bearer {api_key}"}
        if self._client is not None:
            return await self._client.post(
                url, json=payload, headers=headers, timeout=self._request_timeout
            )
        async with httpx.AsyncClient(
            timeout=self._request_timeout, trust_env=self._trust_env
        ) as client:
            return await client.post(url, json=payload, headers=headers)

    async def _get(self, url: str, *, api_key: str | None = None) -> httpx.Response:
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        if self._client is not None:
            return await self._client.get(url, headers=headers, timeout=self._request_timeout)
        async with httpx.AsyncClient(
            timeout=self._request_timeout, trust_env=self._trust_env
        ) as client:
            return await client.get(url, headers=headers)
