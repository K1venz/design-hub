import importlib.util
from importlib import import_module
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

_MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "migrations"
    / "versions"
    / "c6d7e8f9a0b1_admin_public_showcase.py"
)


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("showcase_migration", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except FileNotFoundError:
        pytest.fail("showcase migration is missing")
    return module


def test_showcase_migration_adds_safe_defaults_and_query_index() -> None:
    metadata = sa.MetaData()
    listing_image = sa.Table(
        "listing_image",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("moderation_status", sa.String(16), nullable=False),
    )
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        metadata.create_all(connection)
        connection.execute(
            listing_image.insert(),
            [{"id": 1, "moderation_status": "normal"}],
        )
        migration = _load_migration()
        cast(Any, migration).op = Operations(MigrationContext.configure(connection))
        migration.upgrade()

        row = connection.exec_driver_sql(
            "select is_public_showcase, showcase_download_allowed "
            "from listing_image where id = 1"
        ).one()
        columns = {
            column["name"]: column
            for column in sa.inspect(connection).get_columns("listing_image")
        }
        indexes = {
            index["name"]
            for index in sa.inspect(connection).get_indexes("listing_image")
        }

    assert tuple(row) == (0, 0)
    assert {
        "is_public_showcase",
        "showcase_download_allowed",
        "showcase_preview_key",
        "showcase_preview_width",
        "showcase_preview_height",
        "showcased_at",
        "showcased_by",
    } <= set(columns)
    assert columns["showcase_preview_key"]["nullable"] is True
    assert columns["showcased_at"]["nullable"] is True
    assert "ix_listing_image_public_showcase" in indexes


def test_showcase_orm_and_audit_action_match_migration() -> None:
    models = import_module("design_hub.infrastructure.db.models")
    admin = import_module("design_hub.domain.admin")

    assert {
        "is_public_showcase",
        "showcase_download_allowed",
        "showcase_preview_key",
        "showcase_preview_width",
        "showcase_preview_height",
        "showcased_at",
        "showcased_by",
    } <= set(models.ListingImageRow.__table__.columns.keys())
    assert admin.AdminAction.IMAGE_SHOWCASE_UPDATE.value == "image.showcase.update"
