"""ModelConfigRepository 的 SQLAlchemy 实现（WP-H）。纯写 model_config 行，不改表结构。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from design_hub.domain.admin import AdminAction
from design_hub.domain.errors import DomainError, NotFoundError
from design_hub.infrastructure.db.models import AdminAuditLogRow, ModelConfig
from design_hub.ports.model_config_repository import ModelConfigRecord, ModelConfigRepository


def _to_record(row: ModelConfig) -> ModelConfigRecord:
    return ModelConfigRecord(
        name=row.name, unit_cost=row.unit_cost, enabled=row.enabled, extra=dict(row.extra),
        provider_type=row.provider_type, base_url=row.base_url, model=row.model,
        api_key_env=row.api_key_env, is_default=row.is_default,
    )


def _audit_snapshot(row: ModelConfig) -> dict[str, object]:
    return {
        "name": row.name,
        "unit_cost": str(row.unit_cost),
        "enabled": row.enabled,
        "provider_type": row.provider_type,
        "base_url": row.base_url,
        "model": row.model,
        "api_key_env": row.api_key_env,
        "is_default": row.is_default,
    }


def _audit(
    session: AsyncSession,
    *,
    actor_id: int,
    action: AdminAction,
    name: str,
    before: dict[str, object] | None,
    after: dict[str, object] | None,
) -> None:
    session.add(
        AdminAuditLogRow(
            id=uuid4().hex,
            actor_user_id=actor_id,
            action=action.value,
            target_type="model",
            target_id=name,
            before=before,
            after=after,
        )
    )


class SqlAlchemyModelConfigRepository(ModelConfigRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list_all(self) -> list[ModelConfigRecord]:
        async with self._session_factory() as session:
            rows = (
                await session.execute(select(ModelConfig).order_by(ModelConfig.name))
            ).scalars().all()
            return [_to_record(r) for r in rows]

    async def get(self, name: str) -> ModelConfigRecord | None:
        async with self._session_factory() as session:
            row = await session.get(ModelConfig, name)
            return _to_record(row) if row is not None else None

    async def update(
        self,
        *,
        actor_id: int,
        name: str,
        unit_cost: Decimal | None = None,
        enabled: bool | None = None,
        extra: Mapping[str, Any] | None = None,
        provider_type: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        api_key_env: str | None = None,
    ) -> ModelConfigRecord:
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.get(ModelConfig, name)
                if row is None:
                    raise NotFoundError(f"model config {name} not found")
                before = _audit_snapshot(row)
                if unit_cost is not None:
                    row.unit_cost = unit_cost
                if enabled is not None:
                    row.enabled = enabled
                if extra is not None:
                    row.extra = dict(extra)
                if provider_type is not None:
                    row.provider_type = provider_type
                if base_url is not None:
                    row.base_url = base_url
                if model is not None:
                    row.model = model
                if api_key_env is not None:
                    row.api_key_env = api_key_env
                _audit(
                    session,
                    actor_id=actor_id,
                    action=AdminAction.MODEL_UPDATE,
                    name=name,
                    before=before,
                    after=_audit_snapshot(row),
                )
                await session.flush()
                result = _to_record(row)
        return result

    async def create(
        self,
        *,
        actor_id: int,
        record: ModelConfigRecord,
    ) -> ModelConfigRecord:
        async with self._session_factory() as session:
            async with session.begin():
                if await session.get(ModelConfig, record.name) is not None:
                    raise DomainError(
                        f"model config {record.name} already exists"
                    )
                row = ModelConfig(
                    name=record.name,
                    unit_cost=record.unit_cost,
                    enabled=record.enabled,
                    extra=dict(record.extra),
                    provider_type=record.provider_type,
                    base_url=record.base_url,
                    model=record.model,
                    api_key_env=record.api_key_env,
                    is_default=record.is_default,
                )
                session.add(row)
                _audit(
                    session,
                    actor_id=actor_id,
                    action=AdminAction.MODEL_CREATE,
                    name=record.name,
                    before=None,
                    after=_audit_snapshot(row),
                )
                await session.flush()
                result = _to_record(row)
        return result

    async def delete(self, *, actor_id: int, name: str) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.get(ModelConfig, name)
                if row is None:
                    raise NotFoundError(f"model config {name} not found")
                _audit(
                    session,
                    actor_id=actor_id,
                    action=AdminAction.MODEL_DELETE,
                    name=name,
                    before=_audit_snapshot(row),
                    after=None,
                )
                await session.delete(row)
                await session.flush()

    async def set_default(
        self,
        *,
        actor_id: int,
        name: str,
    ) -> ModelConfigRecord:
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.get(ModelConfig, name)
                if row is None:
                    raise NotFoundError(f"model config {name} not found")
                before = _audit_snapshot(row)
                await session.execute(
                    sa_update(ModelConfig).values(is_default=False)
                )
                row.is_default = True
                _audit(
                    session,
                    actor_id=actor_id,
                    action=AdminAction.MODEL_DEFAULT_SET,
                    name=name,
                    before=before,
                    after=_audit_snapshot(row),
                )
                await session.flush()
                result = _to_record(row)
        return result

    async def seed_defaults(self, defaults: Sequence[ModelConfigRecord]) -> None:
        async with self._session_factory() as session:
            existing = set(
                (await session.execute(select(ModelConfig.name))).scalars().all()
            )
            added = False
            for d in defaults:
                if d.name in existing:
                    continue
                session.add(
                    ModelConfig(
                        name=d.name, unit_cost=d.unit_cost, enabled=d.enabled, extra=dict(d.extra),
                        provider_type=d.provider_type, base_url=d.base_url, model=d.model,
                        api_key_env=d.api_key_env, is_default=d.is_default,
                    )
                )
                added = True
            if added:
                await session.commit()
