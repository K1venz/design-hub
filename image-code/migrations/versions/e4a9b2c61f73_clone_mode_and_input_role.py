"""clone_mode + input role columns (爆款复刻 PRD §3.13)

Revision ID: e4a9b2c61f73
Revises: c7d2f5a18e60
Create Date: 2026-06-10

用户已签字的 2 列（群聊 #559「推进」）：listing_job.clone_mode（历史复刻档徽标）+
listing_job_input.role（product|reference 双角色回显）。全部 additive、可空、零数据删改。
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'e4a9b2c61f73'
down_revision: str | None = 'c7d2f5a18e60'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('listing_job') as batch_op:
        # 参考风格|高度复刻；NULL=非复刻 job
        batch_op.add_column(sa.Column('clone_mode', sa.String(length=16), nullable=True))
    with op.batch_alter_table('listing_job_input') as batch_op:
        # product|reference；NULL=旧数据/非复刻 job
        batch_op.add_column(sa.Column('role', sa.String(length=16), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('listing_job_input') as batch_op:
        batch_op.drop_column('role')
    with op.batch_alter_table('listing_job') as batch_op:
        batch_op.drop_column('clone_mode')
