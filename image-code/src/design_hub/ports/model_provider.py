from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Literal

from design_hub.domain.models import GeneratedImage, ReferenceImage
from design_hub.ports.model_calls import ModelCallContext

# 参考图输入模态（ISSUE-0065）：同步 provider 收字节走 multipart；异步 provider 收现签 URL 走 JSON。
ReferenceMode = Literal["bytes", "url"]


class ProviderError(Exception):
    """Model provider failure (network/IO domain — fallback is allowed here)."""


class ProviderTimeout(ProviderError):
    """Provider exceeded its latency budget."""


class AbstractModelProvider(ABC):
    """模型适配端口（ISP：唯一抽象方法 generate）。"""

    name: str
    unit_cost: Decimal  # CNY per image
    is_live: bool = True  # 真实出图 Provider；占位/测试替身(Mock)置 False，供保真链路拒绝降级
    # 参考图模态（ISSUE-0065）：执行侧按此只物化 ReferenceImage 所需字段——
    # bytes=载字节走 multipart（同步），url=签公网 URL 走 JSON（异步 worker 回拉）。
    reference_mode: ReferenceMode = "bytes"

    @abstractmethod
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
        ...
