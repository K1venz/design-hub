from dataclasses import dataclass
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


class GenerationWorkRepository(Protocol):
    async def submit(self, submission: JobSubmission) -> SubmitResult: ...
