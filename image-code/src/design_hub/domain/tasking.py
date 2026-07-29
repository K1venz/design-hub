from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import ClassVar

from design_hub.domain.enums import ModelName


class OperationType(StrEnum):
    GENERATE_IMAGE = "generate_image"
    CLONE_IMAGE = "clone_image"
    EDIT_IMAGE = "edit_image"
    REPLACE_BACKGROUND = "replace_background"


class RenderTier(StrEnum):
    STANDARD = "standard"
    FOUR_K = "4k"


class ReferenceSource(StrEnum):
    UPLOAD = "upload"
    GENERATED = "generated"


class GenerationItemStatus(StrEnum):
    WAITING = "waiting"
    QUEUED = "queued"
    CLAIMED = "claimed"
    SUBMITTING = "submitting"
    SUBMITTED = "submitted"
    PROCESSING = "processing"
    STORING = "storing"
    GENERATED = "generated"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    FAILED = "failed"
    SUBMISSION_UNCERTAIN = "submission_uncertain"


_TERMINAL_STATUSES = frozenset(
    {
        GenerationItemStatus.GENERATED,
        GenerationItemStatus.CANCELLED,
        GenerationItemStatus.TIMED_OUT,
        GenerationItemStatus.FAILED,
        GenerationItemStatus.SUBMISSION_UNCERTAIN,
    }
)

_TRANSITIONS: dict[GenerationItemStatus, frozenset[GenerationItemStatus]] = {
    GenerationItemStatus.WAITING: frozenset(
        {GenerationItemStatus.QUEUED, GenerationItemStatus.CANCELLED}
    ),
    GenerationItemStatus.QUEUED: frozenset(
        {GenerationItemStatus.CLAIMED, GenerationItemStatus.CANCELLED}
    ),
    GenerationItemStatus.CLAIMED: frozenset(
        {
            GenerationItemStatus.SUBMITTING,
            GenerationItemStatus.CANCELLED,
            GenerationItemStatus.TIMED_OUT,
            GenerationItemStatus.FAILED,
        }
    ),
    GenerationItemStatus.SUBMITTING: frozenset(
        {
            GenerationItemStatus.SUBMITTED,
            GenerationItemStatus.PROCESSING,
            GenerationItemStatus.STORING,
            GenerationItemStatus.TIMED_OUT,
            GenerationItemStatus.FAILED,
            GenerationItemStatus.SUBMISSION_UNCERTAIN,
        }
    ),
    GenerationItemStatus.SUBMITTED: frozenset(
        {
            GenerationItemStatus.PROCESSING,
            GenerationItemStatus.CANCELLED,
            GenerationItemStatus.TIMED_OUT,
            GenerationItemStatus.FAILED,
        }
    ),
    GenerationItemStatus.PROCESSING: frozenset(
        {
            GenerationItemStatus.STORING,
            GenerationItemStatus.CANCELLED,
            GenerationItemStatus.TIMED_OUT,
            GenerationItemStatus.FAILED,
        }
    ),
    GenerationItemStatus.STORING: frozenset(
        {GenerationItemStatus.GENERATED, GenerationItemStatus.FAILED}
    ),
    GenerationItemStatus.GENERATED: frozenset(),
    GenerationItemStatus.CANCELLED: frozenset(),
    GenerationItemStatus.TIMED_OUT: frozenset(),
    GenerationItemStatus.FAILED: frozenset(),
    GenerationItemStatus.SUBMISSION_UNCERTAIN: frozenset(),
}


class InvalidTaskTransition(ValueError):
    pass


class InvalidTaskMessage(ValueError):
    pass


def is_terminal(status: GenerationItemStatus) -> bool:
    return status in _TERMINAL_STATUSES


def require_transition(
    current: GenerationItemStatus, target: GenerationItemStatus
) -> None:
    if target not in _TRANSITIONS[current]:
        raise InvalidTaskTransition(f"illegal generation item transition: {current} -> {target}")


@dataclass(frozen=True)
class ReferenceSnapshot:
    source: ReferenceSource
    object_key: str
    role: str
    order: int

    def __post_init__(self) -> None:
        if not self.object_key:
            raise ValueError("reference object_key must not be empty")
        if not self.role:
            raise ValueError("reference role must not be empty")
        if self.order < 0:
            raise ValueError("reference order must be non-negative")


@dataclass(frozen=True)
class GenerationItemSpec:
    item_id: str
    operation_id: str
    sequence: int
    image_type: str | None
    operation_type: OperationType
    render_tier: RenderTier
    final_prompt: str
    model: ModelName
    ratio: str
    size: tuple[int, int]
    quality: str | None
    seed: int
    references: tuple[ReferenceSnapshot, ...]
    reserved_cost: Decimal

    def __post_init__(self) -> None:
        if not self.item_id:
            raise ValueError("item_id must not be empty")
        if not self.operation_id:
            raise ValueError("operation_id must not be empty")
        if self.sequence < 1:
            raise ValueError("sequence must be positive")
        if not self.final_prompt:
            raise ValueError("final_prompt must not be empty")
        if not self.ratio:
            raise ValueError("ratio must not be empty")
        if self.size[0] <= 0 or self.size[1] <= 0:
            raise ValueError("size dimensions must be positive")
        if self.reserved_cost < 0:
            raise ValueError("reserved_cost must be non-negative")


@dataclass(frozen=True)
class TaskMessage:
    schema_version: int
    message_id: str
    trace_id: str
    request_id: str
    job_id: str
    item_id: str
    operation_id: str
    operation_type: OperationType
    user_id: str
    created_at: datetime

    _FIELD_NAMES: ClassVar[frozenset[str]] = frozenset(
        {
            "schema_version",
            "message_id",
            "trace_id",
            "request_id",
            "job_id",
            "item_id",
            "operation_id",
            "operation_type",
            "user_id",
            "created_at",
        }
    )

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise InvalidTaskMessage(
                f"unsupported task message schema_version: {self.schema_version}"
            )
        identifiers = (
            self.message_id,
            self.trace_id,
            self.request_id,
            self.job_id,
            self.item_id,
            self.operation_id,
            self.user_id,
        )
        if any(not value for value in identifiers):
            raise InvalidTaskMessage("task message identifiers must not be empty")
        if self.created_at.tzinfo is None:
            raise InvalidTaskMessage("task message created_at must be timezone-aware")

    def to_redis_fields(self) -> dict[str, str]:
        created_at = self.created_at.astimezone(UTC).isoformat().replace("+00:00", "Z")
        return {
            "schema_version": str(self.schema_version),
            "message_id": self.message_id,
            "trace_id": self.trace_id,
            "request_id": self.request_id,
            "job_id": self.job_id,
            "item_id": self.item_id,
            "operation_id": self.operation_id,
            "operation_type": self.operation_type.value,
            "user_id": self.user_id,
            "created_at": created_at,
        }

    @classmethod
    def from_redis_fields(cls, fields: Mapping[str, str]) -> "TaskMessage":
        if frozenset(fields) != cls._FIELD_NAMES:
            missing = sorted(cls._FIELD_NAMES - fields.keys())
            unknown = sorted(fields.keys() - cls._FIELD_NAMES)
            raise InvalidTaskMessage(
                f"invalid task message fields: missing={missing}, unknown={unknown}"
            )
        try:
            created_at = datetime.fromisoformat(fields["created_at"].replace("Z", "+00:00"))
            return cls(
                schema_version=int(fields["schema_version"]),
                message_id=fields["message_id"],
                trace_id=fields["trace_id"],
                request_id=fields["request_id"],
                job_id=fields["job_id"],
                item_id=fields["item_id"],
                operation_id=fields["operation_id"],
                operation_type=OperationType(fields["operation_type"]),
                user_id=fields["user_id"],
                created_at=created_at,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise InvalidTaskMessage("invalid task message value") from exc
