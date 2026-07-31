"""Rebuild the live model registry.

Revision ID: d7e8f9a0b1c2
Revises: b8c9d0e1f2a3
"""

from collections.abc import Sequence
from decimal import Decimal

import sqlalchemy as sa
from alembic import op

revision: str = "d7e8f9a0b1c2"
down_revision: str | None = "b8c9d0e1f2a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("model_config")
    op.create_table(
        "model_config",
        sa.Column("name", sa.String(length=64), primary_key=True),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("model_type", sa.String(length=16), nullable=False),
        sa.Column("provider_type", sa.String(length=32), nullable=False),
        sa.Column("base_url", sa.String(length=255), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("credentials_ciphertext", sa.JSON(), nullable=False),
        sa.Column("unit_cost", sa.Numeric(10, 4), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("verified_fingerprint", sa.String(length=64)),
        sa.Column("extra", sa.JSON(), nullable=False),
        sa.UniqueConstraint("model_type", "name", name="uq_model_config_type_name"),
    )
    op.create_index("ix_model_config_model_type", "model_config", ["model_type"])
    op.create_table(
        "model_default",
        sa.Column("model_type", sa.String(length=16), primary_key=True),
        sa.Column("model_name", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["model_type", "model_name"],
            ["model_config.model_type", "model_config.name"],
            name="fk_model_default_same_type",
        ),
    )

    model_config = sa.table(
        "model_config",
        sa.column("name", sa.String),
        sa.column("display_name", sa.String),
        sa.column("model_type", sa.String),
        sa.column("provider_type", sa.String),
        sa.column("base_url", sa.String),
        sa.column("model", sa.String),
        sa.column("credentials_ciphertext", sa.JSON),
        sa.column("unit_cost", sa.Numeric(10, 4)),
        sa.column("enabled", sa.Boolean),
        sa.column("revision", sa.Integer),
        sa.column("extra", sa.JSON),
    )
    op.bulk_insert(
        model_config,
        [
            {
                "name": "gpt-image-2",
                "display_name": "GPT Image",
                "model_type": "image",
                "provider_type": "openai_compat_image",
                "base_url": "",
                "model": "gpt-image-2",
                "credentials_ciphertext": {},
                "unit_cost": Decimal("0.0500"),
                "enabled": False,
                "revision": 1,
                "extra": {},
            },
            {
                "name": "wan2.7-image-pro",
                "display_name": "Wan",
                "model_type": "image",
                "provider_type": "dashscope_wan_image",
                "base_url": "",
                "model": "wan2.7-image-pro",
                "credentials_ciphertext": {},
                "unit_cost": Decimal("0.5000"),
                "enabled": False,
                "revision": 1,
                "extra": {},
            },
            {
                "name": "doubao-chat",
                "display_name": "Doubao",
                "model_type": "chat",
                "provider_type": "openai_compat_chat",
                "base_url": "",
                "model": "doubao-chat",
                "credentials_ciphertext": {},
                "unit_cost": Decimal("0.0000"),
                "enabled": False,
                "revision": 1,
                "extra": {},
            },
        ],
    )
    model_default = sa.table(
        "model_default",
        sa.column("model_type", sa.String),
        sa.column("model_name", sa.String),
    )
    op.bulk_insert(
        model_default,
        [
            {"model_type": "image", "model_name": "gpt-image-2"},
            {"model_type": "chat", "model_name": "doubao-chat"},
        ],
    )


def downgrade() -> None:
    op.drop_table("model_default")
    op.drop_index("ix_model_config_model_type", table_name="model_config")
    op.drop_table("model_config")
