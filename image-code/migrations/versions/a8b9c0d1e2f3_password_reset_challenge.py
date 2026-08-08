"""Add password_reset_challenge for email code reset.

Revision ID: a8b9c0d1e2f3
Revises: c6d7e8f9a0b1
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a8b9c0d1e2f3"
down_revision: str | None = "c6d7e8f9a0b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "password_reset_challenge",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
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


def downgrade() -> None:
    op.drop_index(
        "ix_password_reset_challenge_email",
        table_name="password_reset_challenge",
    )
    op.drop_table("password_reset_challenge")
