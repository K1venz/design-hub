"""listing_job 加 category 列（ISSUE-0060 五品类，用户亲签 schema）

generate/clone 出图落各自品类档，供历史配方复用（jobToRecipe→RecipeView→recipeToPrefill）
+ chat get_job_recipe 回显；edit/legacy 行留 NULL（编辑继承链根语境，不重述品类）。
仅加一列、可空、不改现有列——存量行回填 NULL，零回归。与 c9e4a1b73d52 同批迁移轮跑。

Revision ID: d1a2b3c4e5f6
Revises: c9e4a1b73d52
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d1a2b3c4e5f6"
down_revision: str | None = "c9e4a1b73d52"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "listing_job",
        sa.Column("category", sa.String(length=16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("listing_job", "category")
