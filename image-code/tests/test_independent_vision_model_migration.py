import importlib.util
from datetime import UTC, datetime
from decimal import Decimal
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
    / "b5c6d7e8f9a0_independent_vision_model.py"
)


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "independent_vision_model",
        _MIGRATION_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _schema() -> tuple[sa.Engine, sa.Table, sa.Table]:
    metadata = sa.MetaData()
    model_config = sa.Table(
        "model_config",
        metadata,
        sa.Column("name", sa.String(64), primary_key=True),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("model_type", sa.String(16), nullable=False),
        sa.Column("provider_type", sa.String(32), nullable=False),
        sa.Column("base_url", sa.String(255), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("credentials_ciphertext", sa.JSON, nullable=False),
        sa.Column("unit_cost", sa.Numeric(10, 4), nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_fingerprint", sa.String(64), nullable=True),
        sa.Column("extra", sa.JSON, nullable=False),
        sa.UniqueConstraint("model_type", "name"),
    )
    model_default = sa.Table(
        "model_default",
        metadata,
        sa.Column("model_type", sa.String(16), primary_key=True),
        sa.Column("model_name", sa.String(64), nullable=False),
    )
    engine = sa.create_engine("sqlite://")
    metadata.create_all(engine)
    return engine, model_config, model_default


def test_migration_clones_encrypted_doubao_connection_as_disabled_vision_model() -> None:
    engine, model_config, model_default = _schema()
    encrypted = {"api_key": "ciphertext-that-must-not-be-decrypted"}
    with engine.begin() as connection:
        connection.execute(
            model_config.insert().values(
                name="doubao-chat",
                display_name="Doubao",
                model_type="chat",
                provider_type="openai_compat_chat",
                base_url="https://ark.cn-beijing.volces.com/api/v3",
                model="ep-existing-chat",
                credentials_ciphertext=encrypted,
                unit_cost=Decimal("0"),
                enabled=True,
                revision=4,
                verified_at=datetime.now(UTC),
                verified_fingerprint="a" * 64,
                extra={"thinking_disabled": True},
            )
        )
        migration = _load_migration()
        cast(Any, migration).op = Operations(
            MigrationContext.configure(connection)
        )

        migration.upgrade()

        vision = connection.execute(
            sa.select(model_config).where(
                model_config.c.name == "doubao-vision"
            )
        ).mappings().one()
        assert vision["display_name"] == "豆包 Seed 2.0 Lite 视觉"
        assert vision["model_type"] == "vision"
        assert vision["provider_type"] == "openai_compat_chat"
        assert vision["base_url"] == "https://ark.cn-beijing.volces.com/api/v3"
        assert vision["model"] == "doubao-seed-2-0-lite-260428"
        assert vision["credentials_ciphertext"] == encrypted
        assert vision["enabled"] is False
        assert vision["revision"] == 1
        assert vision["verified_at"] is None
        assert vision["verified_fingerprint"] is None
        assert vision["extra"] == {"thinking_disabled": True}
        assert connection.execute(sa.select(model_default)).all() == [
            ("vision", "doubao-vision")
        ]

        migration.downgrade()

        assert connection.execute(
            sa.select(model_config.c.name).where(
                model_config.c.name == "doubao-vision"
            )
        ).all() == []
        assert connection.execute(sa.select(model_default)).all() == []


def test_migration_skips_vision_default_when_doubao_source_is_absent() -> None:
    engine, model_config, model_default = _schema()
    with engine.begin() as connection:
        migration = _load_migration()
        cast(Any, migration).op = Operations(
            MigrationContext.configure(connection)
        )

        migration.upgrade()

        assert connection.execute(sa.select(model_config)).all() == []
        assert connection.execute(sa.select(model_default)).all() == []


def test_migration_revision_extends_current_head() -> None:
    migration = _load_migration()

    assert migration.revision == "b5c6d7e8f9a0"
    assert migration.down_revision == "a4b5c6d7e8f9"
