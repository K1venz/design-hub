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
    / "f3a4b5c6d7e8_apinebula_async_base_url.py"
)
_OLD_BASE_URL = "https://apinebula.com/v1"
_NEW_BASE_URL = "https://apinebula.ai/v1"


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("apinebula_base_url_migration", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migrates_only_exact_apinebula_async_base_url() -> None:
    metadata = sa.MetaData()
    model_config = sa.Table(
        "model_config",
        metadata,
        sa.Column("name", sa.String, primary_key=True),
        sa.Column("provider_type", sa.String, nullable=False),
        sa.Column("base_url", sa.String, nullable=False),
    )
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        metadata.create_all(connection)
        connection.execute(
            model_config.insert(),
            [
                {
                    "name": "async-old",
                    "provider_type": "apinebula_async_image",
                    "base_url": _OLD_BASE_URL,
                },
                {
                    "name": "sync-old",
                    "provider_type": "openai_compat_image",
                    "base_url": _OLD_BASE_URL,
                },
                {
                    "name": "async-other",
                    "provider_type": "apinebula_async_image",
                    "base_url": "https://relay.example/v1",
                },
            ],
        )
        migration = _load_migration()
        cast(Any, migration).op = Operations(MigrationContext.configure(connection))

        migration.upgrade()
        upgraded = {
            name: base_url
            for name, base_url in connection.execute(
                sa.select(model_config.c.name, model_config.c.base_url)
            )
        }
        assert upgraded == {
            "async-old": _NEW_BASE_URL,
            "sync-old": _OLD_BASE_URL,
            "async-other": "https://relay.example/v1",
        }

        migration.downgrade()
        downgraded = {
            name: base_url
            for name, base_url in connection.execute(
                sa.select(model_config.c.name, model_config.c.base_url)
            )
        }
        assert downgraded == {
            "async-old": _OLD_BASE_URL,
            "sync-old": _OLD_BASE_URL,
            "async-other": "https://relay.example/v1",
        }
