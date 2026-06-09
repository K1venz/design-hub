"""customer owner isolation (ISSUE-0041)

Revision ID: 9b3e1a0c4d41
Revises: 6420ac5f02e7
Create Date: 2026-06-09

客户档案 owner 隔离（用户拍定客户私有）：customer 表加 user_id 列。
现存客户均为无 owner 的遗留测试数据（含"拍拍熊"，用户已批清空）→ 先清表再加 NOT NULL 列。
⚠️ FK：project.customer_id → customer.id 为 ondelete=CASCADE，DELETE FROM customer 会
级联删依赖的退役 project + 其 brief/asset/revision（均为旧流退役测试数据，prod 实测仅 1 套）。
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = '9b3e1a0c4d41'
down_revision: str | None = '6420ac5f02e7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 先清无主遗留客户（含"拍拍熊"，FK CASCADE 连带删退役 project 链）→ 空表再加 NOT NULL 列
    op.execute('DELETE FROM customer')
    # batch 模式跨库：SQLite 重建表、MySQL 普通 ALTER（空表加 NOT NULL 列两库都安全）
    with op.batch_alter_table('customer') as batch_op:
        batch_op.add_column(sa.Column('user_id', sa.String(length=64), nullable=False))
        batch_op.create_index(batch_op.f('ix_customer_user_id'), ['user_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('customer') as batch_op:
        batch_op.drop_index(batch_op.f('ix_customer_user_id'))
        batch_op.drop_column('user_id')
