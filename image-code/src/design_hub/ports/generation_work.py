from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from design_hub.domain.errors import DomainError
from design_hub.domain.models import ListingJobStart
from design_hub.domain.tasking import GenerationItemSpec


class IdempotencyConflict(DomainError):
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
    payload: Mapping[str, str]
    created_at: datetime
    publish_attempts: int


class GenerationWorkRepository(Protocol):
    async def submit(self, submission: JobSubmission) -> SubmitResult: ...

    async def fetch_outbox_batch(
        self, *, limit: int
    ) -> tuple[OutboxRecord, ...]: ...

    async def mark_outbox_published(
        self, event_id: str, redis_id: str
    ) -> None: ...

    async def record_outbox_failure(
        self, event_id: str, error: str
    ) -> None: ...
