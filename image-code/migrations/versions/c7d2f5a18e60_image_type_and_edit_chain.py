"""image_type (套图 PRD §3.12.14) + edit chain columns (二次编辑 ISSUE-0040)

Revision ID: c7d2f5a18e60
Revises: 9b3e1a0c4d41
Create Date: 2026-06-10

用户已签字的 4 列（群聊 #487/#497，套图 1 列 + 二次编辑 3 列一次签）：
全部 additive、可空、零数据删改。batch 模式跨库（SQLite 重建表 / MySQL 普通 ALTER）。
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'c7d2f5a18e60'
down_revision: str | None = '9b3e1a0c4d41'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('listing_image') as batch_op:
        # 图型标签（白底/场景/卖点）；NULL=单图流/套图前旧数据
        batch_op.add_column(sa.Column('image_type', sa.String(length=16), nullable=True))
    with op.batch_alter_table('listing_job') as batch_op:
        # 二次编辑迭代链（ISSUE-0040，列先行、功能随其设计三方对实现）
        batch_op.add_column(sa.Column('parent_job_id', sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column('source_image_key', sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column('edit_mode', sa.String(length=8), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('listing_job') as batch_op:
        batch_op.drop_column('edit_mode')
        batch_op.drop_column('source_image_key')
        batch_op.drop_column('parent_job_id')
    with op.batch_alter_table('listing_image') as batch_op:
        batch_op.drop_column('image_type')
