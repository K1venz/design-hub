"""Move APINebula async image providers to the current API domain.

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
    sa.column("provider_type", sa.String),
    sa.column("base_url", sa.String),
)
_OLD_BASE_URL = "https://apinebula.com/v1"
_NEW_BASE_URL = "https://apinebula.ai/v1"
_ASYNC_PROVIDER_TYPE = "apinebula_async_image"


def upgrade() -> None:
    op.execute(
        _model_config.update()
        .where(_model_config.c.provider_type == _ASYNC_PROVIDER_TYPE)
        .where(_model_config.c.base_url == _OLD_BASE_URL)
        .values(base_url=_NEW_BASE_URL)
    )


def downgrade() -> None:
    # Forward-only: reverting every current URL would corrupt rows that already used it.
    pass
