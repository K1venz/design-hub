"""chat history persistence (ISSUE-0051)

Revision ID: b3f8c1a24d90
Revises: a1f7c3d9e5b2
Create Date: 2026-07-02

用户亲签两表 schema（2026-07-02）：新增 chat_session + chat_message，**零改现有表**。
手写（非 autogenerate）避免 sqlite 反射对现有表造假 diff（沿 ISSUE-0030 先例）。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'b3f8c1a24d90'
down_revision: str | None = 'a1f7c3d9e5b2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'chat_session',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('user_id', sa.String(length=64), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_chat_session_user_id'), 'chat_session', ['user_id'], unique=False)
    op.create_index(op.f('ix_chat_session_updated_at'), 'chat_session', ['updated_at'], unique=False)
    op.create_table(
        'chat_message',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('session_id', sa.String(length=32), nullable=False),
        sa.Column('seq', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(length=16), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('job_id', sa.String(length=32), nullable=True),
        sa.Column('attachment_upload_ids', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['chat_session.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_chat_message_session_id'), 'chat_message', ['session_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_chat_message_session_id'), table_name='chat_message')
    op.drop_table('chat_message')
    op.drop_index(op.f('ix_chat_session_updated_at'), table_name='chat_session')
    op.drop_index(op.f('ix_chat_session_user_id'), table_name='chat_session')
    op.drop_table('chat_session')
