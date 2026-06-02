"""业务指标埋点端口（DIP，WP-监控/ISSUE-0008）。

application 只依赖本抽象；prometheus 实现落 infrastructure。默认 NoopMetricsSink
保持全 Mock dev/CI 零依赖、行为不变。
"""

from abc import ABC, abstractmethod
from decimal import Decimal


class MetricsSink(ABC):
    """出图业务指标落点。HTTP/系统指标由 instrumentator 自动采集，不经此端口。"""

    @abstractmethod
    def record_generation(
        self,
        *,
        model: str,
        mode: str,
        image_count: int,
        cost: Decimal,
        latency_ms: int,
    ) -> None:
        ...


class NoopMetricsSink(MetricsSink):
    """空实现（默认）：dev/CI 不引入 prometheus 依赖、不埋点。"""

    def record_generation(
        self, *, model: str, mode: str, image_count: int, cost: Decimal, latency_ms: int
    ) -> None:
        return None
