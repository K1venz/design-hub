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
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from design_hub.infrastructure.db.base import Base


class ModelConfig(Base):
    __tablename__ = "model_config"

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    extra: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # 配置大模型（ISSUE-0057 档A 注册表制，用户亲签 schema）：每行=一个可用出图模型的连接配置。
    provider_type: Mapped[str] = mapped_column(String(32), default="openai_compat_image")
    base_url: Mapped[str] = mapped_column(String(255), default="")  # 中转站 endpoint
    model: Mapped[str] = mapped_column(String(64), default="")  # 传给上游 API 的模型 id
    # A1 密钥不入库：仅存持有真 key 的环境变量名（真 key 留 server .env、chmod600）
    api_key_env: Mapped[str] = mapped_column(String(64), default="")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)  # 出图默认模型（恰一 true）


class CostLedgerEntry(Base):
    __tablename__ = "cost_ledger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 4))  # +预扣 / -回滚（append-only）
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class AppUser(Base):
    """自建邮箱密码认证用户（ISSUE-0015，替换 OAuth）。"""

    __tablename__ = "app_user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)  # 登录标识
    password_hash: Mapped[str] = mapped_column(String(255))  # bcrypt
    name: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(16), default="设计师")  # 设计师 | 管理者
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ── listing 一键出图：任务持久化 + 历史（ISSUE-0030，B 专表，与海报流彻底分开）──


class ListingJobRow(Base):
    """一次 listing 出图任务（与 generation_job 无关，独立专表）。"""

    __tablename__ = "listing_job"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    prompt: Mapped[str] = mapped_column(Text)  # 用户自由文本（卖点&要求）
    modifiers: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    platform: Mapped[str | None] = mapped_column(String(32), index=True, default=None)  # 冗余,筛选
    # 品类保真档（ISSUE-0060 五品类，用户亲签 schema）：generate/clone 落各自品类，供历史
    # 配方复用 + chat get_job_recipe 回显；edit/legacy 行 = NULL（编辑继承链根语境、不重述品类）
    category: Mapped[str | None] = mapped_column(String(16), default=None)
    model: Mapped[str] = mapped_column(String(64))
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
    inputs: Mapped[list["ListingJobInputRow"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class ListingImageRow(Base):
    """listing 任务下每张候选图（存 image_key 文件名，不存绝对 url，便于 OSS 零迁移）。"""

    __tablename__ = "listing_image"

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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    job: Mapped["ListingJobRow"] = relationship(back_populates="images")


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
