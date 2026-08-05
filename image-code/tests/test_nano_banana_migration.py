import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

_MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "migrations"
    / "versions"
    / "a4b5c6d7e8f9_nano_banana_2_skeleton.py"
)


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "nano_banana_2_skeleton", _MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_adds_disabled_secret_free_nano_skeleton_reversibly() -> None:
    metadata = sa.MetaData()
    model_config = sa.Table(
        "model_config",
        metadata,
        sa.Column("name", sa.String, primary_key=True),
        sa.Column("display_name", sa.String, nullable=False),
        sa.Column("model_type", sa.String, nullable=False),
        sa.Column("provider_type", sa.String, nullable=False),
        sa.Column("base_url", sa.String, nullable=False),
        sa.Column("model", sa.String, nullable=False),
        sa.Column("credentials_ciphertext", sa.JSON, nullable=False),
        sa.Column("unit_cost", sa.Numeric(10, 4), nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("extra", sa.JSON, nullable=False),
    )
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        metadata.create_all(connection)
        migration = _load_migration()
        cast(Any, migration).op = Operations(
            MigrationContext.configure(connection)
        )

        migration.upgrade()
        row = connection.execute(sa.select(model_config)).mappings().one()
        assert dict(row) == {
            "name": "nano-banana-2",
            "display_name": "Nano Banana 2",
            "model_type": "image",
            "provider_type": "gemini_native_image",
            "base_url": "",
            "model": "gemini-3.1-flash-image",
            "credentials_ciphertext": {},
            "unit_cost": 0,
            "enabled": False,
            "revision": 1,
            "extra": {},
        }

        migration.downgrade()
        assert connection.execute(sa.select(model_config)).all() == []


def test_migration_revision_extends_current_head() -> None:
    migration = _load_migration()

    assert migration.revision == "a4b5c6d7e8f9"
    assert migration.down_revision == "d7e8f9a0b1c2"
