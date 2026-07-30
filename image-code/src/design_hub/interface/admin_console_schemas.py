from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict

from design_hub.domain.admin import ModerationReason, ModerationStatus
from design_hub.domain.enums import Role
from design_hub.ports.admin_console import (
    AdminAuditEntry,
    AdminImageSummary,
    AdminJobDetail,
    AdminJobImage,
    AdminJobSummary,
    AdminOverview,
    AdminUserDetail,
    AdminUserSummary,
    ModelCallDetail,
    ModelCallSummary,
    Page,
)
from design_hub.ports.media_url_signer import MediaUrlSigner


class PageOut[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int

    @classmethod
    def of(cls, page: Page[Any], items: list[T]) -> "PageOut[T]":
        return cls(
            items=items,
            total=page.total,
            limit=page.limit,
            offset=page.offset,
        )


class AdminOverviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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

    @classmethod
    def of(cls, value: AdminOverview) -> "AdminOverviewOut":
        return cls.model_validate(value)


class AdminUserSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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

    @classmethod
    def of(cls, value: AdminUserSummary) -> "AdminUserSummaryOut":
        return cls.model_validate(value)


class AdminUserDetailOut(AdminUserSummaryOut):
    disabled_at: datetime | None
    disabled_by: int | None
    disabled_reason: str | None

    @classmethod
    def from_detail(
        cls,
        value: AdminUserDetail,
    ) -> "AdminUserDetailOut":
        return cls.model_validate(value)


class AdminJobSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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
    preview_url: str | None
    created_at: datetime
    completed_at: datetime | None

    @classmethod
    def of(
        cls,
        value: AdminJobSummary,
        signer: MediaUrlSigner,
    ) -> "AdminJobSummaryOut":
        return cls(
            **{
                key: field
                for key, field in value.__dict__.items()
                if key != "first_image_key"
            },
            preview_url=(
                signer.generated_url(value.first_image_key)
                if value.first_image_key is not None
                else None
            ),
        )


class AdminJobInputOut(BaseModel):
    key: str
    role: str | None
    url: str


class AdminJobImageOut(BaseModel):
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
    url: str

    @classmethod
    def of(
        cls,
        value: AdminJobImage,
        signer: MediaUrlSigner,
    ) -> "AdminJobImageOut":
        return cls(
            **value.__dict__,
            url=signer.generated_url(value.image_key),
        )


class ImageModerationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ModerationStatus
    reason: ModerationReason | None = None
    note: str | None = None


class AdminGenerationItemOut(BaseModel):
    item_id: str
    operation_type: str
    model: str
    status: str
    final_prompt: str
    attempt_count: int
    error_code: str | None
    error_detail: str | None


class AdminJobDetailOut(AdminJobSummaryOut):
    prompt: str
    modifiers: dict[str, object]
    error: str | None
    inputs: list[AdminJobInputOut]
    images: list[AdminJobImageOut]
    generation_items: list[AdminGenerationItemOut]

    @classmethod
    def from_detail(
        cls,
        value: AdminJobDetail,
        signer: MediaUrlSigner,
    ) -> "AdminJobDetailOut":
        summary = AdminJobSummaryOut.of(value, signer)
        return cls(
            **summary.model_dump(),
            prompt=value.prompt,
            modifiers=value.modifiers,
            error=value.error,
            inputs=[
                AdminJobInputOut(
                    key=item.key,
                    role=item.role,
                    url=signer.upload_url(item.key),
                )
                for item in value.inputs
            ],
            images=[
                AdminJobImageOut.of(item, signer) for item in value.images
            ],
            generation_items=[
                AdminGenerationItemOut.model_validate(
                    item,
                    from_attributes=True,
                )
                for item in value.generation_items
            ],
        )


class AdminImageSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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
    url: str

    @classmethod
    def of(
        cls,
        value: AdminImageSummary,
        signer: MediaUrlSigner,
    ) -> "AdminImageSummaryOut":
        return cls(
            **value.__dict__,
            url=signer.generated_url(value.image_key),
        )


class ModelCallSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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

    @classmethod
    def of(cls, value: ModelCallSummary) -> "ModelCallSummaryOut":
        return cls.model_validate(value)


class ModelCallSummaryListOut(BaseModel):
    models: list[ModelCallSummaryOut]


class ModelCallDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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

    @classmethod
    def of(cls, value: ModelCallDetail) -> "ModelCallDetailOut":
        return cls.model_validate(value)


class AdminAuditEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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

    @classmethod
    def of(cls, value: AdminAuditEntry) -> "AdminAuditEntryOut":
        return cls.model_validate(value)
