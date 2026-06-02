"""add app_user table

Revision ID: 4a2a261611d9
Revises: f12587232511
Create Date: 2026-06-02 20:06:59.905505

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = '4a2a261611d9'
down_revision: str | None = 'f12587232511'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_user",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False, server_default="设计师"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("email", name="uq_app_user_email"),
    )


def downgrade() -> None:
    op.drop_table("app_user")
