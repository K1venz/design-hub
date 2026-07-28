from dataclasses import dataclass


class RedisUnavailable(RuntimeError):
    pass


class AdmissionRejected(RuntimeError):
    pass


@dataclass
class RedisHealthState:
    stale_after_seconds: float
    _checked_at: float | None = None
    _healthy: bool = False
    _error: str | None = None

    def __post_init__(self) -> None:
        if self.stale_after_seconds <= 0:
            raise ValueError("stale_after_seconds must be positive")

    def mark_healthy(self, *, now: float) -> None:
        self._checked_at = now
        self._healthy = True
        self._error = None

    def mark_unhealthy(self, error: str, *, now: float) -> None:
        self._checked_at = now
        self._healthy = False
        self._error = error[:1000]

    def require_available(self, *, now: float) -> None:
        if self._checked_at is None:
            raise RedisUnavailable("Redis health has not been checked")
        if now - self._checked_at > self.stale_after_seconds:
            raise RedisUnavailable("Redis health status is stale")
        if not self._healthy:
            raise RedisUnavailable(self._error or "Redis is unavailable")


@dataclass(frozen=True)
class AdmissionResult:
    state: str
    estimated_wait_seconds: int


@dataclass(frozen=True)
class QueueAdmissionController:
    soft_wait_seconds: int
    confirm_wait_seconds: int
    hard_depth: int

    def __post_init__(self) -> None:
        if not 0 < self.soft_wait_seconds < self.confirm_wait_seconds:
            raise ValueError("wait thresholds must be positive and ordered")
        if self.hard_depth <= 0:
            raise ValueError("hard_depth must be positive")

    def evaluate(
        self,
        *,
        queue_depth: int,
        rolling_item_seconds: float,
        available_slots: int,
    ) -> AdmissionResult:
        if queue_depth < 0 or rolling_item_seconds < 0:
            raise ValueError("queue inputs must be non-negative")
        if available_slots <= 0:
            raise ValueError("available_slots must be positive")
        if queue_depth >= self.hard_depth:
            raise AdmissionRejected("generation queue reached hard capacity")
        estimated = int(queue_depth * rolling_item_seconds // available_slots)
        if estimated > self.confirm_wait_seconds:
            state = "confirmation_required"
        elif estimated >= self.soft_wait_seconds:
            state = "high_peak"
        else:
            state = "normal"
        return AdmissionResult(state=state, estimated_wait_seconds=estimated)
