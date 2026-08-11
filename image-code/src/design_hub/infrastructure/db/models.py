"""ORM 模型（infrastructure 细节，领域层保持 persistence-ignorant）。

方言无关：仅用 SQLAlchemy 通用类型，MySQL 现用 / PG 后切只改连接串。
字段原则（PRD §5.1）：高频查询字段独立成列，扩展/多选用 JSON。
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
    true,
)
from sqlalchemy.dialects.mysql import DATETIME as MySqlDateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from design_hub.infrastructure.db.base import Base

REGISTRATION_DATETIME = DateTime(timezone=True).with_variant(
    MySqlDateTime(fsp=6),
    "mysql",
)
PASSWORD_RESET_DATETIME = REGISTRATION_DATETIME


class ModelConfig(Base):
    __tablename__ = "model_config"
    __table_args__ = (UniqueConstraint("model_type", "name", name="uq_model_config_type_name"),)

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(128))
    model_type: Mapped[str] = mapped_column(String(16), index=True)
    provider_type: Mapped[str] = mapped_column(String(32))
    base_url: Mapped[str] = mapped_column(String(255))
    model: Mapped[str] = mapped_column(String(128))
    credentials_ciphertext: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_fingerprint: Mapped[str | None] = mapped_column(String(64))
    extra: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ModelDefault(Base):
    __tablename__ = "model_default"
    __table_args__ = (
        ForeignKeyConstraint(
            ["model_type", "model_name"],
            ["model_config.model_type", "model_config.name"],
            name="fk_model_default_same_type",
        ),
    )

    model_type: Mapped[str] = mapped_column(String(16), primary_key=True)
    model_name: Mapped[str] = mapped_column(String(64))


class CostLedgerEntry(Base):
    __tablename__ = "cost_ledger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    operation_id: Mapped[str] = mapped_column(String(128), unique=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 4))  # +预扣 / -回滚（append-only）
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class AppUser(Base):
    """自建邮箱密码认证用户（ISSUE-0015，替换 OAuth）。"""

    __tablename__ = "app_user"
    __table_args__ = (UniqueConstraint("email", name="uq_app_user_email"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(255))  # bcrypt
    name: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(16), default="设计师")  # 设计师 | 管理者
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=true(),
    )
    disabled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        default=None,
    )
    disabled_by: Mapped[int | None] = mapped_column(Integer, default=None)
    disabled_reason: Mapped[str | None] = mapped_column(String(500), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PasswordResetChallengeRow(Base):
    """Single atomic password-reset delivery claim per email."""

    __tablename__ = "password_reset_challenge"
    __table_args__ = (
        UniqueConstraint("email", name="uq_password_reset_challenge_email"),
        UniqueConstraint("delivery_id", name="uq_password_reset_challenge_delivery_id"),
        CheckConstraint(
            "attempt_count >= 0",
            name="ck_password_reset_challenge_attempt_count_nonnegative",
        ),
        CheckConstraint(
            "delivery_state IN ('pending_delivery', 'active', 'consumed')",
            name="ck_password_reset_challenge_delivery_state",
        ),
        Index("ix_password_reset_challenge_consumed_at", "consumed_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    delivery_id: Mapped[str] = mapped_column(String(64))
    email: Mapped[str] = mapped_column(String(255))
    code_hash: Mapped[str] = mapped_column(String(64))
    delivery_state: Mapped[str] = mapped_column(String(32))
    expires_at: Mapped[datetime] = mapped_column(PASSWORD_RESET_DATETIME)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        PASSWORD_RESET_DATETIME,
        server_default=func.now(),
    )
    delivery_claimed_at: Mapped[datetime] = mapped_column(PASSWORD_RESET_DATETIME)
    activated_at: Mapped[datetime | None] = mapped_column(PASSWORD_RESET_DATETIME, default=None)
    consumed_at: Mapped[datetime | None] = mapped_column(PASSWORD_RESET_DATETIME, default=None)


class RegistrationChallengeRow(Base):
    """Registration data whose code is verifiable only after delivery activation."""

    __tablename__ = "registration_challenge"
    __table_args__ = (
        UniqueConstraint("email", name="uq_registration_challenge_email"),
        CheckConstraint(
            "attempt_count >= 0",
            name="ck_registration_challenge_attempt_count_nonnegative",
        ),
        CheckConstraint(
            "delivery_state IN ('pending_delivery', 'active', 'consumed')",
            name="ck_registration_challenge_delivery_state",
        ),
        Index("ix_registration_challenge_consumed_at", "consumed_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    delivery_id: Mapped[str] = mapped_column(String(64), unique=True)
    email: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(128))
    password_hash: Mapped[str] = mapped_column(String(255))
    code_hash: Mapped[str] = mapped_column(String(64))
    delivery_state: Mapped[str] = mapped_column(String(32))
    expires_at: Mapped[datetime] = mapped_column(REGISTRATION_DATETIME)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(REGISTRATION_DATETIME, server_default=func.now())
    delivery_claimed_at: Mapped[datetime] = mapped_column(REGISTRATION_DATETIME)
    activated_at: Mapped[datetime | None] = mapped_column(REGISTRATION_DATETIME, default=None)
    consumed_at: Mapped[datetime | None] = mapped_column(REGISTRATION_DATETIME, default=None)


# ── listing 一键出图：任务持久化 + 历史（ISSUE-0030，B 专表，与海报流彻底分开）──


class ListingJobRow(Base):
    """一次 listing 出图任务（与 generation_job 无关，独立专表）。"""

    __tablename__ = "listing_job"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_listing_job_user_idempotency"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    prompt: Mapped[str] = mapped_column(Text)  # 用户自由文本（卖点&要求）
    modifiers: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    platform: Mapped[str | None] = mapped_column(String(32), index=True, default=None)  # 冗余,筛选
    # 品类保真档（ISSUE-0060 五品类，用户亲签 schema）：generate/clone 落各自品类，供历史
    # 配方复用 + chat get_job_recipe 回显；edit/legacy 行 = NULL（编辑继承链根语境、不重述品类）
    category: Mapped[str | None] = mapped_column(String(16), default=None)
    ratio: Mapped[str] = mapped_column(String(16))
    size: Mapped[str] = mapped_column(String(16))  # 形如 1024x1536
    n: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), index=True)  # 生成中|完成|部分完成|失败
    total_cost: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    error: Mapped[str | None] = mapped_column(Text, default=None)
    # 二次编辑迭代链（ISSUE-0040，列先行）：NULL=首次出图
    parent_job_id: Mapped[str | None] = mapped_column(String(32), default=None)
    source_image_key: Mapped[str | None] = mapped_column(String(128), default=None)
    edit_mode: Mapped[str | None] = mapped_column(String(8), default=None)  # delta|full
    # 复刻档（爆款复刻 PRD §3.13）：参考风格|完全复刻；NULL=非复刻 job
    clone_mode: Mapped[str | None] = mapped_column(String(16), default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    images: Mapped[list["ListingImageRow"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    generation_items: Mapped[list["GenerationItemRow"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    inputs: Mapped[list["ListingJobInputRow"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class GenerationItemRow(Base):
    __tablename__ = "generation_item"
    __table_args__ = (
        UniqueConstraint("job_id", "sequence", name="uq_generation_item_job_sequence"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("listing_job.id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer)
    image_type: Mapped[str | None] = mapped_column(String(16), default=None)
    render_tier: Mapped[str] = mapped_column(String(16))
    operation_type: Mapped[str] = mapped_column(String(32))
    final_prompt: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(64))
    ratio: Mapped[str] = mapped_column(String(16))
    size: Mapped[str] = mapped_column(String(16))
    quality: Mapped[str | None] = mapped_column(String(16), default=None)
    seed: Mapped[int] = mapped_column(Integer)
    reference_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    reserved_cost: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    status: Mapped[str] = mapped_column(String(32), index=True)
    operation_id: Mapped[str] = mapped_column(String(64), unique=True)
    worker_id: Mapped[str | None] = mapped_column(String(128), default=None)
    provider: Mapped[str | None] = mapped_column(String(64), default=None)
    provider_task_id: Mapped[str | None] = mapped_column(String(128), default=None)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True, default=None
    )
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64), default=None)
    error_detail: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    job: Mapped["ListingJobRow"] = relationship(back_populates="generation_items")


class OutboxEventRow(Base):
    __tablename__ = "outbox_event"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    aggregate_type: Mapped[str] = mapped_column(String(32))
    aggregate_id: Mapped[str] = mapped_column(String(64), index=True)
    event_type: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True, default=None
    )
    redis_id: Mapped[str | None] = mapped_column(String(64), default=None)
    publish_attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, default=None)


class ListingImageRow(Base):
    """listing 任务下每张候选图（存 image_key 文件名，不存绝对 url，便于 OSS 零迁移）。"""

    __tablename__ = "listing_image"
    __table_args__ = (
        Index(
            "ix_listing_image_public_showcase",
            "is_public_showcase",
            "moderation_status",
            "showcased_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("listing_job.id", ondelete="CASCADE"), index=True
    )
    image_key: Mapped[str] = mapped_column(String(128))  # <sha>.png（展示时拼 base_url/img/key）
    # 白底|场景|卖点；NULL=单图流（PRD §3.12.14）
    image_type: Mapped[str | None] = mapped_column(String(16), default=None)
    seed: Mapped[int] = mapped_column(Integer)
    cost: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    status: Mapped[str] = mapped_column(String(8))  # 成功|失败
    moderation_status: Mapped[str] = mapped_column(
        String(16),
        default="normal",
        server_default="normal",
    )
    moderation_reason: Mapped[str | None] = mapped_column(String(32), default=None)
    moderation_note: Mapped[str | None] = mapped_column(String(500), default=None)
    moderated_by: Mapped[int | None] = mapped_column(Integer, default=None)
    moderated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        default=None,
    )
    is_public_showcase: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=false(),
    )
    showcase_download_allowed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=false(),
    )
    showcase_preview_key: Mapped[str | None] = mapped_column(
        String(128),
        default=None,
    )
    showcase_preview_width: Mapped[int | None] = mapped_column(Integer, default=None)
    showcase_preview_height: Mapped[int | None] = mapped_column(Integer, default=None)
    showcased_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        default=None,
    )
    showcased_by: Mapped[int | None] = mapped_column(Integer, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    job: Mapped["ListingJobRow"] = relationship(back_populates="images")


class ModelCallRow(Base):
    __tablename__ = "model_call"
    __table_args__ = (CheckConstraint("attempt_no >= 1", name="ck_model_call_attempt_no_positive"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(64), index=True)
    modality: Mapped[str] = mapped_column(String(16))
    operation_type: Mapped[str] = mapped_column(String(32), index=True)
    job_id: Mapped[str | None] = mapped_column(String(32), default=None)
    generation_item_id: Mapped[str | None] = mapped_column(String(32), default=None)
    chat_session_id: Mapped[str | None] = mapped_column(String(32), default=None)
    attempt_no: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), index=True)
    provider_request_id: Mapped[str | None] = mapped_column(String(128), default=None)
    input_tokens: Mapped[int | None] = mapped_column(Integer, default=None)
    output_tokens: Mapped[int | None] = mapped_column(Integer, default=None)
    total_tokens: Mapped[int | None] = mapped_column(Integer, default=None)
    input_text_tokens: Mapped[int | None] = mapped_column(Integer, default=None)
    input_image_tokens: Mapped[int | None] = mapped_column(Integer, default=None)
    output_image_tokens: Mapped[int | None] = mapped_column(Integer, default=None)
    error_code: Mapped[str | None] = mapped_column(String(64), default=None)
    error_detail: Mapped[str | None] = mapped_column(String(500), default=None)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        default=None,
    )
    latency_ms: Mapped[int | None] = mapped_column(Integer, default=None)
    platform_cost: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 4),
        default=None,
    )


class AdminAuditLogRow(Base):
    __tablename__ = "admin_audit_log"
    __table_args__ = (Index("ix_admin_audit_log_target", "target_type", "target_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    actor_user_id: Mapped[int] = mapped_column(Integer, index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    target_type: Mapped[str] = mapped_column(String(32))
    target_id: Mapped[str] = mapped_column(String(128))
    before: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    reason: Mapped[str | None] = mapped_column(String(500), default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
    )


class ListingJobInputRow(Base):
    """listing 任务的输入产品图（upload_key），供历史回显。"""

    __tablename__ = "listing_job_input"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("listing_job.id", ondelete="CASCADE"), index=True
    )
    upload_key: Mapped[str] = mapped_column(String(128))
    # product|reference；NULL=旧数据/非复刻（PRD §3.13）
    role: Mapped[str | None] = mapped_column(String(16), default=None)
    ord: Mapped[int] = mapped_column(Integer)

    job: Mapped["ListingJobRow"] = relationship(back_populates="inputs")


# ── 「帮我设计」对话历史持久化（ISSUE-0051，用户亲签 schema 2026-07-02，新增两表·零改现有）──


class ChatSessionRow(Base):
    """一条持久化对话会话（DeerFlow 式多会话存档）。转录事实源；过程态不落库。"""

    __tablename__ = "chat_session"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # uuid4().hex
    user_id: Mapped[str] = mapped_column(String(64), index=True)  # 与 listing_job.user_id 同口径
    title: Mapped[str] = mapped_column(String(255))  # 首条 user 消息截断
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # 最近消息时间（列表倒序）；append_message 时 repo 显式 bump（子表 INSERT 不自动触发本表）
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    messages: Mapped[list["ChatMessageRow"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class ChatMessageRow(Base):
    """会话内一条转录消息（只存 user 消息 + assistant 最终答复，取舍①过程态不落库）。"""

    __tablename__ = "chat_message"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # uuid4().hex
    session_id: Mapped[str] = mapped_column(
        ForeignKey("chat_session.id", ondelete="CASCADE"), index=True
    )
    seq: Mapped[int] = mapped_column(Integer)  # 会话内顺序（回显排序）
    role: Mapped[str] = mapped_column(String(16))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    # 该轮出图 job（→listing_job 回显图；回显时 job_id→image_key→现签 URL，绝不存签名 URL，取舍②）
    job_id: Mapped[str | None] = mapped_column(String(32), default=None)
    # 带图轮用户上传图 id（回显缩略图，走 uploadPreviewUrl）；NULL=无附图
    attachment_upload_ids: Mapped[list[str] | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped["ChatSessionRow"] = relationship(back_populates="messages")
