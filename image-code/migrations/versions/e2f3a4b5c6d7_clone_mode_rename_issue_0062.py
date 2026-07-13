"""clone_mode 存量行改名 '高度复刻'→'完全复刻'（ISSUE-0062 完全复刻改版，用户拍板 B）

复刻档改版：clone_mode 值「高度复刻」重命名为「完全复刻」。本迁移订正 listing_job 存量行，
使历史复刻单详情显示新档名、与 CloneModeRegistry 新常量一致。**纯数据 UPDATE、零 DDL、
可逆**（down 反向订正）。⚠️ 须用户签字后方可跑 prod（coordinator 已递签、PM 盯放行）；代码先行。

Revision ID: e2f3a4b5c6d7
Revises: d1a2b3c4e5f6
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e2f3a4b5c6d7"
down_revision: str | None = "d1a2b3c4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_listing_job = sa.table("listing_job", sa.column("clone_mode", sa.String))


def upgrade() -> None:
    op.execute(
        _listing_job.update()
        .where(_listing_job.c.clone_mode == "高度复刻")
        .values(clone_mode="完全复刻")
    )


def downgrade() -> None:
    op.execute(
        _listing_job.update()
        .where(_listing_job.c.clone_mode == "完全复刻")
        .values(clone_mode="高度复刻")
    )
