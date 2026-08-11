"""Add pending registration challenges.

Revision ID: b9c0d1e2f3a4
Revises: a8b9c0d1e2f3
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "b9c0d1e2f3a4"
down_revision: str | None = "a8b9c0d1e2f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REGISTRATION_DATETIME = sa.DateTime(timezone=True).with_variant(
    mysql.DATETIME(fsp=6),
    "mysql",
)


def upgrade() -> None:
    op.create_table(
        "registration_challenge",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("delivery_id", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("delivery_state", sa.String(length=32), nullable=False),
        sa.Column("expires_at", REGISTRATION_DATETIME, nullable=False),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "created_at",
            REGISTRATION_DATETIME,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("delivery_claimed_at", REGISTRATION_DATETIME, nullable=False),
        sa.Column("activated_at", REGISTRATION_DATETIME),
        sa.Column("consumed_at", REGISTRATION_DATETIME),
        sa.UniqueConstraint("email", name="uq_registration_challenge_email"),
        sa.UniqueConstraint("delivery_id", name="uq_registration_challenge_delivery_id"),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_registration_challenge_attempt_count_nonnegative",
        ),
        sa.CheckConstraint(
            "delivery_state IN ('pending_delivery', 'active', 'consumed')",
            name="ck_registration_challenge_delivery_state",
        ),
    )
    op.create_index(
        "ix_registration_challenge_consumed_at",
        "registration_challenge",
        ["consumed_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_registration_challenge_consumed_at",
        table_name="registration_challenge",
    )
    op.drop_table("registration_challenge")
