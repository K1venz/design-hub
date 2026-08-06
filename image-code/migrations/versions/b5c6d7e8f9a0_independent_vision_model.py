"""Add an independent Doubao vision model configuration.

Revision ID: b5c6d7e8f9a0
Revises: a4b5c6d7e8f9
"""

from collections.abc import Sequence
from decimal import Decimal

import sqlalchemy as sa
from alembic import op

revision: str = "b5c6d7e8f9a0"
down_revision: str | None = "a4b5c6d7e8f9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CHAT_MODEL_ID = "doubao-chat"
_VISION_MODEL_ID = "doubao-vision"
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
    sa.column("verified_at", sa.DateTime(timezone=True)),
    sa.column("verified_fingerprint", sa.String),
    sa.column("extra", sa.JSON),
)
_model_default = sa.table(
    "model_default",
    sa.column("model_type", sa.String),
    sa.column("model_name", sa.String),
)


def upgrade() -> None:
    source = (
        op.get_bind()
        .execute(
            sa.select(
                _model_config.c.base_url,
                _model_config.c.credentials_ciphertext,
                _model_config.c.extra,
            ).where(_model_config.c.name == _CHAT_MODEL_ID)
        )
        .mappings()
        .one_or_none()
    )
    if source is None:
        return
    op.bulk_insert(
        _model_config,
        [
            {
                "name": _VISION_MODEL_ID,
                "display_name": "豆包 Seed 2.0 Lite 视觉",
                "model_type": "vision",
                "provider_type": "openai_compat_chat",
                "base_url": source["base_url"],
                "model": "doubao-seed-2-0-lite-260428",
                "credentials_ciphertext": source[
                    "credentials_ciphertext"
                ],
                "unit_cost": Decimal("0.0000"),
                "enabled": False,
                "revision": 1,
                "verified_at": None,
                "verified_fingerprint": None,
                "extra": source["extra"],
            }
        ],
    )
    op.bulk_insert(
        _model_default,
        [{"model_type": "vision", "model_name": _VISION_MODEL_ID}],
    )


def downgrade() -> None:
    op.execute(
        _model_default.delete().where(
            _model_default.c.model_type == "vision"
        )
    )
    op.execute(
        _model_config.delete().where(
            _model_config.c.name == _VISION_MODEL_ID
        )
    )
