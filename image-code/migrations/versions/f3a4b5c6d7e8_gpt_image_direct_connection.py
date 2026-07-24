"""Move GPT Image 2 to the documented OpenAI-compatible Images API.

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f3a4b5c6d7e8"
down_revision: str | None = "e2f3a4b5c6d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_model_config = sa.table(
    "model_config",
    sa.column("name", sa.String),
    sa.column("provider_type", sa.String),
    sa.column("base_url", sa.String),
    sa.column("model", sa.String),
)
_MIGRATED_ROWS_TABLE = "gpt_image_connection_migration_f3a4b5c6d7e8"
_migrated_rows = sa.table(
    _MIGRATED_ROWS_TABLE,
    sa.column("name", sa.String),
    sa.column("provider_type", sa.String),
    sa.column("base_url", sa.String),
)
_OLD_BASE_URL = "https://apinebula.com/v1"
_CURRENT_ASYNC_BASE_URL = "https://apinebula.ai/v1"
_DIRECT_BASE_URL = "https://api.yhlxj.ai/v1"
_ASYNC_PROVIDER_TYPE = "apinebula_async_image"
_DIRECT_PROVIDER_TYPE = "openai_compat_image"
_MODEL = "gpt-image-2"


def _migration_target() -> sa.ColumnElement[bool]:
    return sa.and_(
        _model_config.c.provider_type == _ASYNC_PROVIDER_TYPE,
        _model_config.c.model == _MODEL,
        _model_config.c.base_url.in_([_OLD_BASE_URL, _CURRENT_ASYNC_BASE_URL]),
    )


def upgrade() -> None:
    op.create_table(
        _MIGRATED_ROWS_TABLE,
        sa.Column("name", sa.String(length=255), primary_key=True),
        sa.Column("provider_type", sa.String(length=64), nullable=False),
        sa.Column("base_url", sa.String(length=512), nullable=False),
    )
    op.execute(
        _migrated_rows.insert().from_select(
            ["name", "provider_type", "base_url"],
            sa.select(
                _model_config.c.name,
                _model_config.c.provider_type,
                _model_config.c.base_url,
            ).where(_migration_target()),
        )
    )
    op.execute(
        _model_config.update()
        .where(_migration_target())
        .values(provider_type=_DIRECT_PROVIDER_TYPE, base_url=_DIRECT_BASE_URL)
    )


def downgrade() -> None:
    original_provider_type = (
        sa.select(_migrated_rows.c.provider_type)
        .where(_migrated_rows.c.name == _model_config.c.name)
        .scalar_subquery()
    )
    original_base_url = (
        sa.select(_migrated_rows.c.base_url)
        .where(_migrated_rows.c.name == _model_config.c.name)
        .scalar_subquery()
    )
    op.execute(
        _model_config.update()
        .where(_model_config.c.name.in_(sa.select(_migrated_rows.c.name)))
        .where(_model_config.c.provider_type == _DIRECT_PROVIDER_TYPE)
        .where(_model_config.c.base_url == _DIRECT_BASE_URL)
        .values(
            provider_type=original_provider_type,
            base_url=original_base_url,
        )
    )
    op.drop_table(_MIGRATED_ROWS_TABLE)
