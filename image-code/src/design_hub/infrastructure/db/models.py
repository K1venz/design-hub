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
    # 复刻档（爆款复刻 PRD §3.13）：参考风格|高度复刻；NULL=非复刻 job
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
