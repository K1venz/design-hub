"""Add admin console persistence.

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b8c9d0e1f2a3"
down_revision: str | None = "a7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("app_user") as batch:
        batch.add_column(
            sa.Column(
                "enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )
        batch.add_column(sa.Column("disabled_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("disabled_by", sa.Integer()))
        batch.add_column(sa.Column("disabled_reason", sa.String(length=500)))

    with op.batch_alter_table("listing_image") as batch:
        batch.add_column(
            sa.Column(
                "moderation_status",
                sa.String(length=16),
                nullable=False,
                server_default="normal",
            )
        )
        batch.add_column(sa.Column("moderation_reason", sa.String(length=32)))
        batch.add_column(sa.Column("moderation_note", sa.String(length=500)))
        batch.add_column(sa.Column("moderated_by", sa.Integer()))
        batch.add_column(sa.Column("moderated_at", sa.DateTime(timezone=True)))

    op.create_table(
        "model_call",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("modality", sa.String(length=16), nullable=False),
        sa.Column("operation_type", sa.String(length=32), nullable=False),
        sa.Column("job_id", sa.String(length=32)),
        sa.Column("generation_item_id", sa.String(length=32)),
        sa.Column("chat_session_id", sa.String(length=32)),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("provider_request_id", sa.String(length=128)),
        sa.Column("input_tokens", sa.Integer()),
        sa.Column("output_tokens", sa.Integer()),
        sa.Column("total_tokens", sa.Integer()),
        sa.Column("input_text_tokens", sa.Integer()),
        sa.Column("input_image_tokens", sa.Integer()),
        sa.Column("output_image_tokens", sa.Integer()),
        sa.Column("error_code", sa.String(length=64)),
        sa.Column("error_detail", sa.String(length=500)),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("platform_cost", sa.Numeric(10, 4)),
        sa.CheckConstraint("attempt_no >= 1", name="ck_model_call_attempt_no_positive"),
    )
    op.create_index("ix_model_call_user_id", "model_call", ["user_id"])
    op.create_index("ix_model_call_model", "model_call", ["model"])
    op.create_index("ix_model_call_operation_type", "model_call", ["operation_type"])
    op.create_index("ix_model_call_status", "model_call", ["status"])
    op.create_index("ix_model_call_started_at", "model_call", ["started_at"])

    op.create_table(
        "admin_audit_log",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("actor_user_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.String(length=128), nullable=False),
        sa.Column("before", sa.JSON()),
        sa.Column("after", sa.JSON()),
        sa.Column("reason", sa.String(length=500)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_admin_audit_log_actor_user_id",
        "admin_audit_log",
        ["actor_user_id"],
    )
    op.create_index("ix_admin_audit_log_action", "admin_audit_log", ["action"])
    op.create_index(
        "ix_admin_audit_log_target",
        "admin_audit_log",
        ["target_type", "target_id"],
    )
    op.create_index("ix_admin_audit_log_created_at", "admin_audit_log", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_admin_audit_log_created_at", table_name="admin_audit_log")
    op.drop_index("ix_admin_audit_log_target", table_name="admin_audit_log")
    op.drop_index("ix_admin_audit_log_action", table_name="admin_audit_log")
    op.drop_index("ix_admin_audit_log_actor_user_id", table_name="admin_audit_log")
    op.drop_table("admin_audit_log")

    op.drop_index("ix_model_call_started_at", table_name="model_call")
    op.drop_index("ix_model_call_status", table_name="model_call")
    op.drop_index("ix_model_call_operation_type", table_name="model_call")
    op.drop_index("ix_model_call_model", table_name="model_call")
    op.drop_index("ix_model_call_user_id", table_name="model_call")
    op.drop_table("model_call")

    with op.batch_alter_table("listing_image") as batch:
        batch.drop_column("moderated_at")
        batch.drop_column("moderated_by")
        batch.drop_column("moderation_note")
        batch.drop_column("moderation_reason")
        batch.drop_column("moderation_status")

    with op.batch_alter_table("app_user") as batch:
        batch.drop_column("disabled_reason")
        batch.drop_column("disabled_by")
        batch.drop_column("disabled_at")
        batch.drop_column("enabled")
