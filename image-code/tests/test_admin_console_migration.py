import importlib.util
from collections.abc import Iterator
from contextlib import contextmanager
from importlib import import_module
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.engine import Connection

_MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "migrations"
    / "versions"
    / "b8c9d0e1f2a3_admin_console_foundation.py"
)


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("admin_console_migration", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except FileNotFoundError:
        pytest.fail("admin console migration is missing")
    return module


@contextmanager
def upgraded_connection() -> Iterator[Connection]:
    metadata = sa.MetaData()
    app_user = sa.Table(
        "app_user",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
    )
    listing_image = sa.Table(
        "listing_image",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
    )
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        metadata.create_all(connection)
        connection.execute(app_user.insert(), [{"id": 1}, {"id": 2}])
        connection.execute(listing_image.insert(), [{"id": 1}, {"id": 2}])
        migration = _load_migration()
        cast(Any, migration).op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        yield connection


def test_admin_console_migration_preserves_safe_defaults() -> None:
    with upgraded_connection() as connection:
        users = connection.exec_driver_sql("select enabled from app_user").all()
        images = connection.exec_driver_sql(
            "select moderation_status from listing_image"
        ).all()

        assert [row[0] for row in users] == [1, 1]
        assert [row[0] for row in images] == ["normal", "normal"]


def test_admin_console_migration_creates_call_and_audit_tables() -> None:
    with upgraded_connection() as connection:
        inspector = sa.inspect(connection)

        assert {"model_call", "admin_audit_log"} <= set(inspector.get_table_names())
        assert {column["name"] for column in inspector.get_columns("model_call")} >= {
            "id",
            "user_id",
            "provider",
            "model",
            "modality",
            "operation_type",
            "attempt_no",
            "status",
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "started_at",
            "completed_at",
        }
        assert {column["name"] for column in inspector.get_columns("admin_audit_log")} >= {
            "id",
            "actor_user_id",
            "action",
            "target_type",
            "target_id",
            "before",
            "after",
            "reason",
            "created_at",
        }


def test_admin_domain_values_are_stable() -> None:
    try:
        admin = import_module("design_hub.domain.admin")
    except ModuleNotFoundError:
        pytest.fail("admin domain types are missing")

    assert [status.value for status in admin.ModerationStatus] == ["normal", "blocked"]
    assert [reason.value for reason in admin.ModerationReason] == [
        "sexual",
        "violence",
        "illegal",
        "infringement",
        "other",
    ]
    assert [status.value for status in admin.ModelCallStatus] == [
        "started",
        "succeeded",
        "failed",
        "uncertain",
        "interrupted",
    ]
    assert [modality.value for modality in admin.ModelModality] == ["image", "chat"]
    assert [operation.value for operation in admin.ModelOperation] == [
        "image_generation",
        "image_edit",
        "chat_completion",
        "reverse_prompt",
    ]


def test_admin_orm_rows_match_the_migration_contract() -> None:
    models = import_module("design_hub.infrastructure.db.models")

    assert set(models.AppUser.__table__.columns.keys()) >= {
        "enabled",
        "disabled_at",
        "disabled_by",
        "disabled_reason",
    }
    assert set(models.ListingImageRow.__table__.columns.keys()) >= {
        "moderation_status",
        "moderation_reason",
        "moderation_note",
        "moderated_by",
        "moderated_at",
    }
    assert models.ModelCallRow.__table__.name == "model_call"
    assert models.AdminAuditLogRow.__table__.name == "admin_audit_log"
