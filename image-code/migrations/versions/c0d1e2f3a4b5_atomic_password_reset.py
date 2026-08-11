"""Make password reset delivery and completion atomic.

Revision ID: c0d1e2f3a4b5
Revises: b9c0d1e2f3a4
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "c0d1e2f3a4b5"
down_revision: str | None = "b9c0d1e2f3a4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RESET_DATETIME = sa.DateTime(timezone=True).with_variant(
    mysql.DATETIME(fsp=6),
    "mysql",
)


def upgrade() -> None:
    # Reset challenges are short-lived credentials and are deliberately invalidated on rollout.
    op.drop_table("password_reset_challenge")
    op.create_table(
        "password_reset_challenge",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("delivery_id", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("delivery_state", sa.String(length=32), nullable=False),
        sa.Column("expires_at", RESET_DATETIME, nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", RESET_DATETIME, nullable=False, server_default=sa.func.now()),
        sa.Column("delivery_claimed_at", RESET_DATETIME, nullable=False),
        sa.Column("activated_at", RESET_DATETIME),
        sa.Column("consumed_at", RESET_DATETIME),
        sa.UniqueConstraint("email", name="uq_password_reset_challenge_email"),
        sa.UniqueConstraint("delivery_id", name="uq_password_reset_challenge_delivery_id"),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_password_reset_challenge_attempt_count_nonnegative",
        ),
        sa.CheckConstraint(
            "delivery_state IN ('pending_delivery', 'active', 'consumed')",
            name="ck_password_reset_challenge_delivery_state",
        ),
    )
    op.create_index(
        "ix_password_reset_challenge_consumed_at",
        "password_reset_challenge",
        ["consumed_at"],
    )


def downgrade() -> None:
    op.drop_table("password_reset_challenge")
    op.create_table(
        "password_reset_challenge",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_password_reset_challenge_email",
        "password_reset_challenge",
        ["email"],
    )
