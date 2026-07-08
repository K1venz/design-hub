"""model_config 扩连接配置列（ISSUE-0057 配置大模型档A，用户亲签 schema）

新增 provider_type/base_url/model/api_key_env/is_default——每行=一个可用出图模型的连接配置
（A1 密钥不入库、仅存 env 名）。仅加列、不改现有列/不删；server_default 使存量行安全回填。

Revision ID: c9e4a1b73d52
Revises: b3f8c1a24d90
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c9e4a1b73d52"
down_revision: str | None = "b3f8c1a24d90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "model_config",
        sa.Column(
            "provider_type", sa.String(length=32), nullable=False,
            server_default="openai_compat_image",
        ),
    )
    op.add_column(
        "model_config",
        sa.Column("base_url", sa.String(length=255), nullable=False, server_default=""),
    )
    op.add_column(
        "model_config",
        sa.Column("model", sa.String(length=64), nullable=False, server_default=""),
    )
    op.add_column(
        "model_config",
        sa.Column("api_key_env", sa.String(length=64), nullable=False, server_default=""),
    )
    op.add_column(
        "model_config",
        sa.Column(
            "is_default", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )


def downgrade() -> None:
    op.drop_column("model_config", "is_default")
    op.drop_column("model_config", "api_key_env")
    op.drop_column("model_config", "model")
    op.drop_column("model_config", "base_url")
    op.drop_column("model_config", "provider_type")
