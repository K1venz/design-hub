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
    / "f3a4b5c6d7e8_gpt_image_direct_connection.py"
)
_OLD_BASE_URL = "https://apinebula.com/v1"
_CURRENT_ASYNC_BASE_URL = "https://apinebula.ai/v1"
_DIRECT_BASE_URL = "https://api.yhlxj.ai/v1"
_ASYNC_PROVIDER = "apinebula_async_image"
_DIRECT_PROVIDER = "openai_compat_image"


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("apinebula_base_url_migration", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migrates_apinebula_gpt_image_to_direct_images_api_reversibly() -> None:
    metadata = sa.MetaData()
    model_config = sa.Table(
        "model_config",
        metadata,
        sa.Column("name", sa.String, primary_key=True),
        sa.Column("provider_type", sa.String, nullable=False),
        sa.Column("base_url", sa.String, nullable=False),
        sa.Column("model", sa.String, nullable=False),
    )
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        metadata.create_all(connection)
        connection.execute(
            model_config.insert(),
            [
                {
                    "name": "async-old",
                    "provider_type": _ASYNC_PROVIDER,
                    "base_url": _OLD_BASE_URL,
                    "model": "gpt-image-2",
                },
                {
                    "name": "async-current",
                    "provider_type": _ASYNC_PROVIDER,
                    "base_url": _CURRENT_ASYNC_BASE_URL,
                    "model": "gpt-image-2",
                },
                {
                    "name": "sync-old",
                    "provider_type": _DIRECT_PROVIDER,
                    "base_url": _OLD_BASE_URL,
                    "model": "gpt-image-2",
                },
                {
                    "name": "async-other",
                    "provider_type": _ASYNC_PROVIDER,
                    "base_url": "https://relay.example/v1",
                    "model": "gpt-image-2",
                },
                {
                    "name": "async-other-model",
                    "provider_type": _ASYNC_PROVIDER,
                    "base_url": _CURRENT_ASYNC_BASE_URL,
                    "model": "other-image-model",
                },
                {
                    "name": "direct-current",
                    "provider_type": _DIRECT_PROVIDER,
                    "base_url": _DIRECT_BASE_URL,
                    "model": "gpt-image-2",
                },
            ],
        )
        migration = _load_migration()
        cast(Any, migration).op = Operations(MigrationContext.configure(connection))

        migration.upgrade()
        upgraded = {
            name: (provider_type, base_url)
            for name, provider_type, base_url in connection.execute(
                sa.select(
                    model_config.c.name,
                    model_config.c.provider_type,
                    model_config.c.base_url,
                )
            )
        }
        assert upgraded == {
            "async-old": (_DIRECT_PROVIDER, _DIRECT_BASE_URL),
            "async-current": (_DIRECT_PROVIDER, _DIRECT_BASE_URL),
            "sync-old": (_DIRECT_PROVIDER, _OLD_BASE_URL),
            "async-other": (_ASYNC_PROVIDER, "https://relay.example/v1"),
            "async-other-model": (_ASYNC_PROVIDER, _CURRENT_ASYNC_BASE_URL),
            "direct-current": (_DIRECT_PROVIDER, _DIRECT_BASE_URL),
        }

        migration.downgrade()
        downgraded = {
            name: (provider_type, base_url)
            for name, provider_type, base_url in connection.execute(
                sa.select(
                    model_config.c.name,
                    model_config.c.provider_type,
                    model_config.c.base_url,
                )
            )
        }
        assert downgraded == {
            "async-old": (_ASYNC_PROVIDER, _OLD_BASE_URL),
            "async-current": (_ASYNC_PROVIDER, _CURRENT_ASYNC_BASE_URL),
            "sync-old": (_DIRECT_PROVIDER, _OLD_BASE_URL),
            "async-other": (_ASYNC_PROVIDER, "https://relay.example/v1"),
            "async-other-model": (_ASYNC_PROVIDER, _CURRENT_ASYNC_BASE_URL),
            "direct-current": (_DIRECT_PROVIDER, _DIRECT_BASE_URL),
        }
