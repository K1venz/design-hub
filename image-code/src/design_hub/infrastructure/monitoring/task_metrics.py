from prometheus_client import REGISTRY, CollectorRegistry, Counter, Gauge, Histogram


class TaskMetrics:
    def __init__(self, *, registry: CollectorRegistry = REGISTRY) -> None:
        self._outbox_pending = Gauge(
            "design_hub_generation_outbox_pending",
            "Unpublished generation outbox records.",
            registry=registry,
        )
        self._outbox_oldest_age = Gauge(
            "design_hub_generation_outbox_oldest_age_seconds",
            "Age of the oldest unpublished generation outbox record.",
            registry=registry,
        )
        self._stream_depth = Gauge(
            "design_hub_generation_stream_depth",
            "Generation stream depth.",
            registry=registry,
        )
        self._stream_pending = Gauge(
            "design_hub_generation_stream_pending",
            "Generation stream pending entries.",
            registry=registry,
        )
        self._item_state = Gauge(
            "design_hub_generation_item_state",
            "Generation items by durable state.",
            labelnames=("status",),
            registry=registry,
        )
        self._item_duration = Histogram(
            "design_hub_generation_item_duration_seconds",
            "Generation item duration by terminal outcome.",
            labelnames=("outcome",),
            buckets=(1, 3, 5, 10, 20, 30, 60, 120, 300, 600, 1200),
            registry=registry,
        )
        self._provider_in_flight = Gauge(
            "design_hub_generation_provider_in_flight",
            "Provider submissions currently in flight.",
            labelnames=("provider", "tier"),
            registry=registry,
        )
        self._submission_uncertain = Counter(
            "design_hub_generation_submission_uncertain",
            "Provider submissions with an ambiguous outcome.",
            labelnames=("provider",),
            registry=registry,
        )
        self._failures = Counter(
            "design_hub_generation_failures",
            "Generation failures by bounded error code.",
            labelnames=("error_code",),
            registry=registry,
        )
        self._sse_connections = Gauge(
            "design_hub_generation_sse_connections",
            "Active listing SSE connections.",
            registry=registry,
        )

    def set_outbox(self, *, pending: int, oldest_age_seconds: float) -> None:
        self._outbox_pending.set(pending)
        self._outbox_oldest_age.set(oldest_age_seconds)

    def set_stream(self, *, depth: int, pending: int) -> None:
        self._stream_depth.set(depth)
        self._stream_pending.set(pending)

    def set_item_state(self, status: str, count: int) -> None:
        self._item_state.labels(status=status).set(count)

    def observe_item_duration(self, outcome: str, seconds: float) -> None:
        self._item_duration.labels(outcome=outcome).observe(seconds)

    def provider_started(self, provider: str, tier: str) -> None:
        self._provider_in_flight.labels(provider=provider, tier=tier).inc()

    def provider_finished(self, provider: str, tier: str) -> None:
        self._provider_in_flight.labels(provider=provider, tier=tier).dec()

    def record_uncertain(self, provider: str) -> None:
        self._submission_uncertain.labels(provider=provider).inc()

    def record_failure(self, error_code: str) -> None:
        self._failures.labels(error_code=error_code).inc()

    def sse_opened(self) -> None:
        self._sse_connections.inc()

    def sse_closed(self) -> None:
        self._sse_connections.dec()


task_metrics = TaskMetrics()
