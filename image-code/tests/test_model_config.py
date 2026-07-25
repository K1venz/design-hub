"""model_config CRUD（ISSUE-0057）：注册表增删改 + set_default 唯一性 + api_key_env 只回名。"""

import asyncio
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from design_hub.application.admin.model_config_service import ModelConfigService
from design_hub.domain.errors import DomainError, NotFoundError
from design_hub.infrastructure.db.base import Base
from design_hub.infrastructure.db.model_config_repo import SqlAlchemyModelConfigRepository
from design_hub.interface.admin_schemas import ModelConfigOut
from design_hub.ports.model_config_repository import ModelConfigRecord


async def _svc() -> ModelConfigService:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sf = async_sessionmaker(engine, expire_on_commit=False)
    return ModelConfigService(repo=SqlAlchemyModelConfigRepository(sf))


def _rec(name: str, **kw) -> ModelConfigRecord:
    base = dict(unit_cost=Decimal("0.40"), enabled=True, extra={},
               provider_type="openai_compat_image", base_url="https://x", model="gpt-image-2",
               api_key_env="GPT_IMAGE_API_KEY", is_default=False)
    base.update(kw)
    return ModelConfigRecord(name=name, **base)  # type: ignore[arg-type]


def test_create_list_and_connection_fields_roundtrip() -> None:
    async def _impl() -> None:
        svc = await _svc()
        await svc.create(_rec("gpt-image-2"))
        rows = await svc.list()
        r = next(x for x in rows if x.name == "gpt-image-2")
        assert r.provider_type == "openai_compat_image" and r.base_url == "https://x"
        assert r.model == "gpt-image-2" and r.api_key_env == "GPT_IMAGE_API_KEY"

    asyncio.run(_impl())


def test_create_duplicate_raises_domain_error() -> None:
    async def _impl() -> None:
        svc = await _svc()
        await svc.create(_rec("m1"))
        with pytest.raises(DomainError):
            await svc.create(_rec("m1"))

    asyncio.run(_impl())


def test_update_provider_fields() -> None:
    async def _impl() -> None:
        svc = await _svc()
        await svc.create(_rec("m1", base_url="https://old"))
        r = await svc.update("m1", base_url="https://new", enabled=False)
        assert r.base_url == "https://new" and r.enabled is False

    asyncio.run(_impl())


def test_set_default_is_exclusive() -> None:
    async def _impl() -> None:
        svc = await _svc()
        await svc.create(_rec("a"))
        await svc.create(_rec("b"))
        await svc.set_default("a")
        await svc.set_default("b")  # 切默认（备用渠道切换）
        rows = {x.name: x.is_default for x in await svc.list()}
        assert rows["b"] is True and rows["a"] is False  # 恰一默认

    asyncio.run(_impl())


def test_delete_and_missing_raises() -> None:
    async def _impl() -> None:
        svc = await _svc()
        await svc.create(_rec("m1"))
        await svc.delete("m1")
        assert all(x.name != "m1" for x in await svc.list())
        with pytest.raises(NotFoundError):
            await svc.delete("m1")

    asyncio.run(_impl())


def test_out_schema_exposes_env_name_never_real_key() -> None:
    # 验收⑦：Out 只有 api_key_env(env 名)，无任何真 key 字段。
    r = _rec("m1", api_key_env="GPT_IMAGE_API_KEY")
    out = ModelConfigOut.of(r).model_dump()
    assert out["api_key_env"] == "GPT_IMAGE_API_KEY"
    assert not any("key" in k and k != "api_key_env" for k in out)


def test_resolve_image_connection_prefers_default_else_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # ISSUE-0057 de-hardcode：兼容协议的默认连接驱动出图；连接空/无默认回落 .env。
    from design_hub.composition import _resolve_image_connection
    from design_hub.config.settings import Settings
    s = Settings(
        gpt_image_base_url="https://envfallback", gpt_image_model="env-model",
        gpt_image_api_key="envkey",
    )
    monkeypatch.setenv("MY_BACKUP_KEY", "dk1,dk2")
    dc = _rec("backup", base_url="https://backup", model="backup-model",
              api_key_env="MY_BACKUP_KEY", unit_cost=Decimal("0.55"), is_default=True)
    base, model, keys = _resolve_image_connection(s, dc)
    assert base == "https://backup" and model == "backup-model"
    assert keys == ["dk1", "dk2"]
    # 无默认 → 回落 .env
    b2, m2, k2 = _resolve_image_connection(s, None)
    assert b2 == "https://envfallback" and m2 == "env-model" and k2 == ["envkey"]
    # 有默认但 env key 未设 → 回落 .env（不拿空 key 起 provider）
    monkeypatch.delenv("MY_BACKUP_KEY", raising=False)
    b3, _, _ = _resolve_image_connection(s, dc)
    assert b3 == "https://envfallback"


def test_4k_wall_clock_budget_is_positive() -> None:
    from design_hub.config.settings import Settings

    assert Settings().gpt_image_4k_timeout == 1800.0
    with pytest.raises(ValidationError):
        Settings(gpt_image_4k_timeout=0.0)
