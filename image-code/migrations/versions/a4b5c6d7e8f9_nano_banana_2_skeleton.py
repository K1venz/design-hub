"""Add the disabled Nano Banana 2 model skeleton.

Revision ID: a4b5c6d7e8f9
Revises: d7e8f9a0b1c2
"""

from collections.abc import Sequence
from decimal import Decimal

import sqlalchemy as sa
from alembic import op

revision: str = "a4b5c6d7e8f9"
down_revision: str | None = "d7e8f9a0b1c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MODEL_ID = "nano-banana-2"
_model_config = sa.table(
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


def upgrade() -> None:
    op.bulk_insert(
        _model_config,
        [
            {
                "name": _MODEL_ID,
                "display_name": "Nano Banana 2",
                "model_type": "image",
                "provider_type": "gemini_native_image",
                "base_url": "",
                "model": "gemini-3.1-flash-image",
                "credentials_ciphertext": {},
                "unit_cost": Decimal("0.0000"),
                "enabled": False,
                "revision": 1,
                "extra": {},
            }
        ],
    )


def downgrade() -> None:
    op.execute(_model_config.delete().where(_model_config.c.name == _MODEL_ID))
