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
    / "d7e8f9a0b1c2_live_model_configuration.py"
)


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("live_model_configuration", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _upgrade_legacy_model_config() -> sa.engine.Connection:
    metadata = sa.MetaData()
    sa.Table(
        "model_config",
        metadata,
        sa.Column("name", sa.String(length=64), primary_key=True),
        sa.Column("unit_cost", sa.Numeric(10, 4), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("extra", sa.JSON(), nullable=False),
        sa.Column("provider_type", sa.String(length=32), nullable=False),
        sa.Column("base_url", sa.String(length=255), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("api_key_env", sa.String(length=64), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
    )
    engine = sa.create_engine("sqlite://")
    connection = engine.connect()
    transaction = connection.begin()
    metadata.create_all(connection)
    migration = _load_migration()
    cast(Any, migration).op = Operations(MigrationContext.configure(connection))
    migration.upgrade()
    transaction.commit()
    return connection


def test_upgrade_rebuilds_model_config_without_legacy_columns() -> None:
    """Dropping a legacy column must also discard the legacy table definition."""
    connection = _upgrade_legacy_model_config()
    try:
        columns = {
            column["name"] for column in sa.inspect(connection).get_columns("model_config")
        }

        assert columns == {
            "name",
            "display_name",
            "model_type",
            "provider_type",
            "base_url",
            "model",
            "credentials_ciphertext",
            "unit_cost",
            "enabled",
            "revision",
            "verified_at",
            "verified_fingerprint",
            "extra",
        }
    finally:
        connection.close()


def test_migration_revision_follows_the_current_head() -> None:
    migration = _load_migration()

    assert migration.revision == "d7e8f9a0b1c2"
    assert migration.down_revision == "b8c9d0e1f2a3"


def test_upgrade_creates_one_default_per_type_with_same_type_foreign_key() -> None:
    """A default must point to a model record of the matching type."""
    connection = _upgrade_legacy_model_config()
    try:
        inspector = sa.inspect(connection)
        defaults = connection.exec_driver_sql(
            "select model_type, model_name from model_default order by model_type"
        ).all()
        foreign_keys = inspector.get_foreign_keys("model_default")

        assert defaults == [("chat", "doubao-chat"), ("image", "gpt-image-2")]
        assert any(
            foreign_key["referred_table"] == "model_config"
            and foreign_key["constrained_columns"] == ["model_type", "model_name"]
            and foreign_key["referred_columns"] == ["model_type", "name"]
            for foreign_key in foreign_keys
        )
    finally:
        connection.close()


def test_upgrade_seeds_only_disabled_non_secret_gpt_wan_and_doubao_skeletons() -> None:
    """The registry starts safe and contains only the approved provider skeletons."""
    connection = _upgrade_legacy_model_config()
    try:
        rows = connection.exec_driver_sql(
            "select name, display_name, model_type, provider_type, base_url, model, "
            "credentials_ciphertext, unit_cost, enabled, revision, extra "
            "from model_config order by name"
        ).mappings().all()

        assert rows == [
            {
                "name": "doubao-chat",
                "display_name": "Doubao",
                "model_type": "chat",
                "provider_type": "openai_compat_chat",
                "base_url": "",
                "model": "doubao-chat",
                "credentials_ciphertext": "{}",
                "unit_cost": 0,
                "enabled": 0,
                "revision": 1,
                "extra": "{}",
            },
            {
                "name": "gpt-image-2",
                "display_name": "GPT Image",
                "model_type": "image",
                "provider_type": "openai_compat_image",
                "base_url": "",
                "model": "gpt-image-2",
                "credentials_ciphertext": "{}",
                "unit_cost": 0.05,
                "enabled": 0,
                "revision": 1,
                "extra": "{}",
            },
            {
                "name": "wan2.7-image-pro",
                "display_name": "Wan",
                "model_type": "image",
                "provider_type": "dashscope_wan_image",
                "base_url": "",
                "model": "wan2.7-image-pro",
                "credentials_ciphertext": "{}",
                "unit_cost": 0.5,
                "enabled": 0,
                "revision": 1,
                "extra": "{}",
            },
        ]
    finally:
        connection.close()


def test_live_model_domain_and_orm_use_stable_typed_model_ids() -> None:
    """The registry must expose typed providers and stable string IDs, not ModelName."""
    from design_hub.domain.enums import ModelType, ProviderType
    from design_hub.domain.model_config import (
        DOUBAO_CHAT,
        GPT_IMAGE_2,
        WAN_2_7_IMAGE_PRO,
    )
    from design_hub.infrastructure.db.models import ModelConfig, ModelDefault

    assert [model_type.value for model_type in ModelType] == ["image", "chat"]
    assert [provider.value for provider in ProviderType] == [
        "openai_compat_image",
        "gemini_native_image",
        "dashscope_wan_image",
        "openai_compat_chat",
    ]
    assert (GPT_IMAGE_2, WAN_2_7_IMAGE_PRO, DOUBAO_CHAT) == (
        "gpt-image-2",
        "wan2.7-image-pro",
        "doubao-chat",
    )
    assert "ModelName" not in __import__("design_hub.domain.enums", fromlist=["*"]).__dict__
    assert set(ModelConfig.__table__.columns.keys()) == {
        "name",
        "display_name",
        "model_type",
        "provider_type",
        "base_url",
        "model",
        "credentials_ciphertext",
        "unit_cost",
        "enabled",
        "revision",
        "verified_at",
        "verified_fingerprint",
        "extra",
    }
    assert ModelDefault.__table__.primary_key.columns.keys() == ["model_type"]
