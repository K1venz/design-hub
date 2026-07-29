from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from design_hub.domain.errors import DomainError
from design_hub.domain.models import GeneratedImage, ListingJobStart
from design_hub.domain.tasking import GenerationItemSpec, GenerationItemStatus


class IdempotencyConflict(DomainError):
    pass


class ConcurrentTaskMutation(DomainError):
    pass


@dataclass(frozen=True)
class JobSubmission:
    job: ListingJobStart
    idempotency_key: str
    request_fingerprint: str
    items: tuple[GenerationItemSpec, ...]
    trace_id: str
    request_id: str


@dataclass(frozen=True)
class SubmitResult:
    job_id: str
    replayed: bool


@dataclass(frozen=True)
class OutboxRecord:
    event_id: str
    payload: Mapping[str, object]
    created_at: datetime
    publish_attempts: int
    aggregate_type: str = "generation_item"
    event_type: str = "generation_item.queued"


@dataclass(frozen=True)
class OutboxStats:
    pending: int
    oldest_created_at: datetime | None


@dataclass(frozen=True)
class GenerationWorkItem:
    job_id: str
    user_id: str
    spec: GenerationItemSpec
    status: GenerationItemStatus
    provider_task_id: str | None
    worker_id: str | None
    lease_expires_at: datetime | None = None


class GenerationWorkRepository(Protocol):
    async def submit(self, submission: JobSubmission) -> SubmitResult: ...

    async def fetch_outbox_batch(
        self, *, limit: int
    ) -> tuple[OutboxRecord, ...]: ...

    async def outbox_stats(self) -> OutboxStats: ...

    async def mark_outbox_published(
        self, event_id: str, redis_id: str
    ) -> None: ...

    async def record_outbox_failure(
        self, event_id: str, error: str
    ) -> None: ...

    async def load_item(self, item_id: str) -> GenerationWorkItem: ...

    async def claim(
        self, item_id: str, worker_id: str, lease_seconds: int
    ) -> None: ...

    async def mark_submitting(
        self, item_id: str, worker_id: str
    ) -> None: ...

    async def mark_submitted(
        self, item_id: str, worker_id: str, provider_task_id: str
    ) -> None: ...

    async def mark_processing(
        self, item_id: str, worker_id: str
    ) -> None: ...

    async def mark_storing(
        self, item_id: str, worker_id: str
    ) -> None: ...

    async def complete_item(
        self, item_id: str, worker_id: str, image: GeneratedImage
    ) -> None: ...

    async def fail_item(
        self,
        item_id: str,
        worker_id: str,
        error_code: str,
        error_detail: str,
    ) -> None: ...

    async def mark_submission_uncertain(
        self, item_id: str, worker_id: str, error_detail: str
    ) -> None: ...

    async def heartbeat(
        self, item_id: str, worker_id: str, lease_seconds: int
    ) -> None: ...

    async def cancel_item(self, item_id: str, user_id: str) -> None: ...
