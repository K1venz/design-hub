from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from design_hub.domain.enums import Role


@dataclass(frozen=True)
class Page[T]:
    items: tuple[T, ...]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True)
class DateRange:
    start: datetime
    end: datetime


@dataclass(frozen=True)
class AdminUserFilter:
    q: str | None = None
    role: Role | None = None
    enabled: bool | None = None


@dataclass(frozen=True)
class AdminJobFilter:
    user_id: int | None = None
    status: str | None = None
    model: str | None = None
    operation_type: str | None = None
    date_range: DateRange | None = None


@dataclass(frozen=True)
class AdminImageFilter:
    user_id: int | None = None
    model: str | None = None
    operation_type: str | None = None
    status: str | None = None
    moderation_status: str | None = None
    date_range: DateRange | None = None


@dataclass(frozen=True)
class ModelCallFilter:
    user_id: int | None = None
    provider: str | None = None
    model: str | None = None
    modality: str | None = None
    operation_type: str | None = None
    status: str | None = None
    date_range: DateRange | None = None


@dataclass(frozen=True)
class AdminAuditFilter:
    actor_user_id: int | None = None
    action: str | None = None
    target_type: str | None = None
    date_range: DateRange | None = None


@dataclass(frozen=True)
class AdminOverview:
    start: datetime
    end: datetime
    registered_users: int
    active_users: int
    jobs: int
    successful_images: int
    image_calls: int
    image_succeeded: int
    image_failed: int
    image_uncertain: int
    image_retries: int
    chat_calls: int
    chat_input_tokens: int
    chat_output_tokens: int
    chat_total_tokens: int
    platform_cost: Decimal
    average_latency_ms: float | None
    failure_rate: float


@dataclass(frozen=True)
class AdminUserSummary:
    user_id: int
    email: str
    name: str
    role: Role
    enabled: bool
    created_at: datetime
    last_activity_at: datetime | None
    jobs: int
    successful_images: int
    image_calls: int
    chat_calls: int
    chat_total_tokens: int
    platform_cost: Decimal


@dataclass(frozen=True)
class AdminUserDetail(AdminUserSummary):
    disabled_at: datetime | None
    disabled_by: int | None
    disabled_reason: str | None


@dataclass(frozen=True)
class AdminJobSummary:
    job_id: str
    user_id: int
    user_email: str
    user_name: str
    status: str
    operation_type: str | None
    model: str | None
    ratio: str
    size: str
    requested_images: int
    successful_images: int
    total_cost: Decimal
    first_image_key: str | None
    created_at: datetime
    completed_at: datetime | None


@dataclass(frozen=True)
class AdminJobInput:
    key: str
    role: str | None


@dataclass(frozen=True)
class AdminJobImage:
    image_id: int
    image_key: str
    image_type: str | None
    status: str
    moderation_status: str
    moderation_reason: str | None
    moderation_note: str | None
    moderated_by: int | None
    moderated_at: datetime | None
    cost: Decimal
    created_at: datetime


@dataclass(frozen=True)
class AdminGenerationItem:
    item_id: str
    operation_type: str
    model: str
    status: str
    final_prompt: str
    attempt_count: int
    error_code: str | None
    error_detail: str | None


@dataclass(frozen=True)
class AdminJobDetail(AdminJobSummary):
    prompt: str
    modifiers: dict[str, object]
    error: str | None
    inputs: tuple[AdminJobInput, ...]
    images: tuple[AdminJobImage, ...]
    generation_items: tuple[AdminGenerationItem, ...]


@dataclass(frozen=True)
class AdminImageSummary:
    image_id: int
    image_key: str
    job_id: str
    user_id: int
    user_email: str
    user_name: str
    image_type: str | None
    status: str
    moderation_status: str
    moderation_reason: str | None
    moderation_note: str | None
    moderated_by: int | None
    moderated_at: datetime | None
    operation_type: str | None
    model: str | None
    cost: Decimal
    created_at: datetime


@dataclass(frozen=True)
class ModelCallSummary:
    provider: str
    model: str
    modality: str
    operation_type: str | None
    calls: int
    succeeded: int
    failed: int
    uncertain: int
    interrupted: int
    retries: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    platform_cost: Decimal
    average_latency_ms: float | None


@dataclass(frozen=True)
class ModelCallDetail:
    call_id: str
    user_id: int
    user_email: str
    provider: str
    model: str
    modality: str
    operation_type: str
    attempt_no: int
    status: str
    provider_request_id: str | None
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    input_text_tokens: int | None
    input_image_tokens: int | None
    output_image_tokens: int | None
    error_code: str | None
    error_detail: str | None
    job_id: str | None
    generation_item_id: str | None
    chat_session_id: str | None
    started_at: datetime
    completed_at: datetime | None
    latency_ms: int | None
    platform_cost: Decimal | None


@dataclass(frozen=True)
class AdminAuditEntry:
    audit_id: str
    actor_user_id: int
    actor_email: str
    action: str
    target_type: str
    target_id: str
    before: dict[str, object] | None
    after: dict[str, object] | None
    reason: str | None
    created_at: datetime


class AdminConsoleRepository(ABC):
    @abstractmethod
    async def overview(self, date_range: DateRange) -> AdminOverview: ...

    @abstractmethod
    async def list_users(
        self,
        filters: AdminUserFilter,
        *,
        limit: int,
        offset: int,
    ) -> Page[AdminUserSummary]: ...

    @abstractmethod
    async def get_user(self, user_id: int) -> AdminUserDetail | None: ...

    @abstractmethod
    async def list_jobs(
        self,
        filters: AdminJobFilter,
        *,
        limit: int,
        offset: int,
    ) -> Page[AdminJobSummary]: ...

    @abstractmethod
    async def get_job(self, job_id: str) -> AdminJobDetail | None: ...

    @abstractmethod
    async def list_images(
        self,
        filters: AdminImageFilter,
        *,
        limit: int,
        offset: int,
    ) -> Page[AdminImageSummary]: ...

    @abstractmethod
    async def summarize_model_calls(
        self,
        filters: ModelCallFilter,
    ) -> tuple[ModelCallSummary, ...]: ...

    @abstractmethod
    async def list_model_calls(
        self,
        filters: ModelCallFilter,
        *,
        limit: int,
        offset: int,
    ) -> Page[ModelCallDetail]: ...

    @abstractmethod
    async def list_audit_logs(
        self,
        filters: AdminAuditFilter,
        *,
        limit: int,
        offset: int,
    ) -> Page[AdminAuditEntry]: ...
