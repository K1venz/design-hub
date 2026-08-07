"""Add manager-controlled public showcase state.

Revision ID: c6d7e8f9a0b1
Revises: b5c6d7e8f9a0
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c6d7e8f9a0b1"
down_revision: str | None = "b5c6d7e8f9a0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "listing_image",
        sa.Column(
            "is_public_showcase",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "listing_image",
        sa.Column(
            "showcase_download_allowed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "listing_image",
        sa.Column("showcase_preview_key", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "listing_image",
        sa.Column("showcase_preview_width", sa.Integer(), nullable=True),
    )
    op.add_column(
        "listing_image",
        sa.Column("showcase_preview_height", sa.Integer(), nullable=True),
    )
    op.add_column(
        "listing_image",
        sa.Column("showcased_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "listing_image",
        sa.Column("showcased_by", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_listing_image_public_showcase",
        "listing_image",
        ["is_public_showcase", "moderation_status", "showcased_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_listing_image_public_showcase", table_name="listing_image")
    op.drop_column("listing_image", "showcased_by")
    op.drop_column("listing_image", "showcased_at")
    op.drop_column("listing_image", "showcase_preview_height")
    op.drop_column("listing_image", "showcase_preview_width")
    op.drop_column("listing_image", "showcase_preview_key")
    op.drop_column("listing_image", "showcase_download_allowed")
    op.drop_column("listing_image", "is_public_showcase")
