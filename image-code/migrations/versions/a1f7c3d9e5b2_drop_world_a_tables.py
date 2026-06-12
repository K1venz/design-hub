"""drop world-A tables (世界 A 移除，ISSUE-0046 纯 toC 自助出图)

Revision ID: a1f7c3d9e5b2
Revises: e4a9b2c61f73
Create Date: 2026-06-12

用户已亲签的 8 表 DROP（群聊 #774；蓝图 56a2083 §3）。children-first 序：
generated_image → generation_job → deliverable → revision → asset → brief
→ project → customer。prod 老表全 0 行（ops #762 清残留核验）=零数据损失。
保 6 张：model_config / cost_ledger / app_user / listing_job / listing_image /
listing_job_input。downgrade 不提供（项目规则：无向后兼容；回滚=全库备份 restore）。
"""
from collections.abc import Sequence

from alembic import op


revision: str = 'a1f7c3d9e5b2'
down_revision: str | None = 'e4a9b2c61f73'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_WORLD_A_TABLES = (  # children-first（FK 依赖序）
    'generated_image',
    'generation_job',
    'deliverable',
    'revision',
    'asset',
    'brief',
    'project',
    'customer',
)


def upgrade() -> None:
    for table in _WORLD_A_TABLES:
        op.drop_table(table)


def downgrade() -> None:
    raise NotImplementedError("世界 A 不可恢复（无向后兼容）；回滚走全库备份 restore")
