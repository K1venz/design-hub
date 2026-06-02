"""MetricsSink 的 Prometheus 实现（WP-监控/ISSUE-0008）。"""

from decimal import Decimal

from design_hub.infrastructure.monitoring import metrics
from design_hub.ports.metrics import MetricsSink


class PrometheusMetricsSink(MetricsSink):
    def record_generation(
        self, *, model: str, mode: str, image_count: int, cost: Decimal, latency_ms: int
    ) -> None:
        metrics.GENERATIONS.labels(model=model, mode=mode).inc()
        metrics.IMAGES.labels(model=model).inc(image_count)
        metrics.COST.labels(model=model).inc(float(cost))
        metrics.LATENCY.labels(model=model).observe(latency_ms / 1000)
