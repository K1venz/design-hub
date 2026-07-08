"""OpenAI 兼容中转站 provider 共用无状态辅助（同步/异步 provider 单一事实源，ISSUE-0065）。

同步 `OpenAICompatImageProvider`（单发 /images/edits）与异步 `AsyncImageTasksProvider`
（submit→轮询→download）走同一上游协议族，HTTP 状态分流 / 负面提示合并 / 退避抖动逻辑共用。
"""

import random

import httpx

from design_hub.domain.enums import ModelName
from design_hub.domain.errors import DomainError
from design_hub.ports.model_provider import ProviderTimeout


def raise_for_status(name: ModelName, response: httpx.Response) -> None:
    """按 status_code 分流（不对错误体调 .json()，诗云 502 是 nginx HTML）：
    2xx 放行；429/5xx→ProviderTimeout（限流/服务端故障，可切同模型备用/重试）；
    其余 4xx（400/401/403/422…）→DomainError（坏请求/鉴权/配置，fail-fast 不切备）。"""
    code = response.status_code
    if 200 <= code < 300:
        return
    snippet = response.text[:200]
    if code == 429 or code >= 500:
        raise ProviderTimeout(f"{name} {code}: {snippet}")
    raise DomainError(f"{name} {code} (不切备): {snippet}")


def compose_prompt(prompt: str, negative_prompt: str) -> str:
    """gpt-image 协议无 negative 字段：把负面约束并入正向文本，避免信息丢失。"""
    if not negative_prompt:
        return prompt
    return f"{prompt}\n（请避免：{negative_prompt}）"


def retry_sleep(attempt: int, *, backoff: float, max_sleep: float) -> float:
    """指数退避 + equal-jitter 抖动（ISSUE-0047）：并发同时撞 429 时错峰去相关重发时刻。
    下界=backoff/2 保底退避量、上界=backoff 加随机扰动；max_sleep 封顶防指数失控。"""
    base = min(max_sleep, backoff * 2.0 ** (attempt - 1))
    return base / 2 + random.uniform(0, base / 2)
