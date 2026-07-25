"""Persist the actual model used by listing jobs.

Revision ID: a4b5c6d7e8f9
Revises: f3a4b5c6d7e8
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a4b5c6d7e8f9"
down_revision: str | None = "f3a4b5c6d7e8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "listing_job",
        sa.Column(
            "model",
            sa.String(length=64),
            nullable=False,
            server_default="gpt-image-2",
        ),
    )
    with op.batch_alter_table("listing_job") as batch_op:
        batch_op.alter_column(
            "model",
            existing_type=sa.String(length=64),
            server_default=None,
        )


def downgrade() -> None:
    op.drop_column("listing_job", "model")
