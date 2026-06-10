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


class Customer(Base):
    __tablename__ = "customer"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)  # owner 隔离（ISSUE-0041）
    name: Mapped[str] = mapped_column(String(128), index=True)
    contact: Mapped[str | None] = mapped_column(String(128), default=None)
    industry: Mapped[str | None] = mapped_column(String(64), default=None)
    brand_color: Mapped[str | None] = mapped_column(String(32), default=None)
    common_styles: Mapped[list[str]] = mapped_column(JSON, default=list)
    common_taboos: Mapped[list[str]] = mapped_column(JSON, default=list)
    common_sizes: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    projects: Mapped[list["Project"]] = relationship(
        back_populates="customer", cascade="all, delete-orphan"
    )


class Project(Base):
    __tablename__ = "project"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customer.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16), index=True, default="需求录入")
    current_round: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    customer: Mapped["Customer"] = relationship(back_populates="projects")
    briefs: Mapped[list["Brief"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    assets: Mapped[list["Asset"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    revisions: Mapped[list["Revision"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    deliverables: Mapped[list["Deliverable"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    jobs: Mapped[list["GenerationJobRow"]] = relationship(back_populates="project")


class Brief(Base):
    __tablename__ = "brief"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE"), index=True
    )
    material_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    sizes: Mapped[list[str]] = mapped_column(JSON, default=list)
    styles: Mapped[list[str]] = mapped_column(JSON, default=list)
    resolution: Mapped[str | None] = mapped_column(String(32), default=None)
    bleed: Mapped[str | None] = mapped_column(String(32), default=None)
    copy_text: Mapped[str | None] = mapped_column(Text, default=None)
    taboo: Mapped[str | None] = mapped_column(Text, default=None)
    delivery: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped["Project"] = relationship(back_populates="briefs")


class Asset(Base):
    __tablename__ = "asset"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(16))
    url: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped["Project"] = relationship(back_populates="assets")


class GenerationJobRow(Base):
    __tablename__ = "generation_job"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("project.id", ondelete="SET NULL"), nullable=True, default=None, index=True
    )
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    customer: Mapped[str] = mapped_column(String(128))
    subscene: Mapped[str] = mapped_column(String(8))
    family: Mapped[str] = mapped_column(String(16), index=True)
    tier: Mapped[str] = mapped_column(String(16), index=True)
    style: Mapped[str] = mapped_column(String(32), index=True)
    category: Mapped[str] = mapped_column(String(32), index=True)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    candidate_count: Mapped[int] = mapped_column(Integer)
    used_model: Mapped[str] = mapped_column(String(32), index=True)
    total_cost: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    positive_prompt: Mapped[str] = mapped_column(Text)
    negative_prompt: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), index=True)
    round_no: Mapped[int] = mapped_column(Integer, default=1)
    extra: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped["Project | None"] = relationship(back_populates="jobs")
    images: Mapped[list["GeneratedImageRow"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class GeneratedImageRow(Base):
    __tablename__ = "generated_image"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("generation_job.id", ondelete="CASCADE"), index=True
    )
    url: Mapped[str] = mapped_column(String(512))
    seed: Mapped[int] = mapped_column(Integer)
    latency_ms: Mapped[int] = mapped_column(Integer)
    cost: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    score: Mapped[int | None] = mapped_column(Integer, default=None)
    kept: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    job: Mapped["GenerationJobRow"] = relationship(back_populates="images")


class Revision(Base):
    __tablename__ = "revision"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE"), index=True
    )
    round_no: Mapped[int] = mapped_column(Integer, default=1)
    items: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), default="进行中")
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped["Project"] = relationship(back_populates="revisions")


class Deliverable(Base):
    __tablename__ = "deliverable"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE"), index=True
    )
    fmt: Mapped[str] = mapped_column(String(16))
    files: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped["Project"] = relationship(back_populates="deliverables")


class ModelConfig(Base):
    __tablename__ = "model_config"

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    extra: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


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
    ord: Mapped[int] = mapped_column(Integer)

    job: Mapped["ListingJobRow"] = relationship(back_populates="inputs")
