"""Add durable per-image generation tasks and transactional outbox.

Revision ID: a7b8c9d0e1f2
Revises: f3a4b5c6d7e8
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7b8c9d0e1f2"
down_revision: str | None = "f3a4b5c6d7e8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("listing_job") as batch:
        batch.add_column(sa.Column("idempotency_key", sa.String(length=128), nullable=True))
        batch.add_column(sa.Column("request_fingerprint", sa.String(length=64), nullable=True))
    listing_job = sa.table(
        "listing_job",
        sa.column("id", sa.String),
        sa.column("idempotency_key", sa.String),
        sa.column("request_fingerprint", sa.String),
    )
    op.execute(
        listing_job.update().values(
            idempotency_key=sa.literal("legacy:") + listing_job.c.id,
            request_fingerprint=sa.literal("legacy:") + listing_job.c.id,
        )
    )
    with op.batch_alter_table("listing_job") as batch:
        batch.alter_column("idempotency_key", existing_type=sa.String(128), nullable=False)
        batch.alter_column("request_fingerprint", existing_type=sa.String(64), nullable=False)
        batch.create_unique_constraint(
            "uq_listing_job_user_idempotency", ["user_id", "idempotency_key"]
        )

    with op.batch_alter_table("cost_ledger") as batch:
        batch.add_column(sa.Column("operation_id", sa.String(length=128), nullable=True))
    cost_ledger = sa.table(
        "cost_ledger",
        sa.column("id", sa.Integer),
        sa.column("operation_id", sa.String),
    )
    op.execute(
        cost_ledger.update().values(
            operation_id=sa.literal("legacy:")
            + sa.cast(cost_ledger.c.id, sa.String(length=32))
        )
    )
    with op.batch_alter_table("cost_ledger") as batch:
        batch.alter_column("operation_id", existing_type=sa.String(128), nullable=False)
        batch.create_unique_constraint("uq_cost_ledger_operation_id", ["operation_id"])

    op.create_table(
        "generation_item",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column(
            "job_id",
            sa.String(length=32),
            sa.ForeignKey("listing_job.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("image_type", sa.String(length=16), nullable=True),
        sa.Column("render_tier", sa.String(length=16), nullable=False),
        sa.Column("operation_type", sa.String(length=32), nullable=False),
        sa.Column("final_prompt", sa.Text(), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("ratio", sa.String(length=16), nullable=False),
        sa.Column("size", sa.String(length=16), nullable=False),
        sa.Column("quality", sa.String(length=16), nullable=True),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("reference_snapshot", sa.JSON(), nullable=False),
        sa.Column("reserved_cost", sa.Numeric(10, 4), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("operation_id", sa.String(length=64), nullable=False),
        sa.Column("worker_id", sa.String(length=128), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("provider_task_id", sa.String(length=128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("job_id", "sequence", name="uq_generation_item_job_sequence"),
        sa.UniqueConstraint("operation_id", name="uq_generation_item_operation_id"),
    )
    op.create_index("ix_generation_item_job_id", "generation_item", ["job_id"])
    op.create_index("ix_generation_item_status", "generation_item", ["status"])
    op.create_index(
        "ix_generation_item_lease_expires_at", "generation_item", ["lease_expires_at"]
    )

    op.create_table(
        "outbox_event",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("aggregate_type", sa.String(length=32), nullable=False),
        sa.Column("aggregate_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("redis_id", sa.String(length=64), nullable=True),
        sa.Column("publish_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
    )
    op.create_index("ix_outbox_event_aggregate_id", "outbox_event", ["aggregate_id"])
    op.create_index("ix_outbox_event_created_at", "outbox_event", ["created_at"])
    op.create_index("ix_outbox_event_published_at", "outbox_event", ["published_at"])


def downgrade() -> None:
    op.drop_index("ix_outbox_event_published_at", table_name="outbox_event")
    op.drop_index("ix_outbox_event_created_at", table_name="outbox_event")
    op.drop_index("ix_outbox_event_aggregate_id", table_name="outbox_event")
    op.drop_table("outbox_event")
    op.drop_index("ix_generation_item_lease_expires_at", table_name="generation_item")
    op.drop_index("ix_generation_item_status", table_name="generation_item")
    op.drop_index("ix_generation_item_job_id", table_name="generation_item")
    op.drop_table("generation_item")
    with op.batch_alter_table("cost_ledger") as batch:
        batch.drop_constraint("uq_cost_ledger_operation_id", type_="unique")
        batch.drop_column("operation_id")
    with op.batch_alter_table("listing_job") as batch:
        batch.drop_constraint("uq_listing_job_user_idempotency", type_="unique")
        batch.drop_column("request_fingerprint")
        batch.drop_column("idempotency_key")
