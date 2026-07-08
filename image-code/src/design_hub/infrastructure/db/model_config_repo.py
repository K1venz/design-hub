"""ModelConfigRepository 的 SQLAlchemy 实现（WP-H）。纯写 model_config 行，不改表结构。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from design_hub.domain.errors import NotFoundError
from design_hub.infrastructure.db.models import ModelConfig
from design_hub.ports.model_config_repository import ModelConfigRecord, ModelConfigRepository


def _to_record(row: ModelConfig) -> ModelConfigRecord:
    return ModelConfigRecord(
        name=row.name, unit_cost=row.unit_cost, enabled=row.enabled, extra=dict(row.extra),
        provider_type=row.provider_type, base_url=row.base_url, model=row.model,
        api_key_env=row.api_key_env, is_default=row.is_default,
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
        name: str,
        *,
        unit_cost: Decimal | None = None,
        enabled: bool | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> ModelConfigRecord:
        async with self._session_factory() as session:
            row = await session.get(ModelConfig, name)
            if row is None:
                raise NotFoundError(f"model config {name} not found")
            if unit_cost is not None:
                row.unit_cost = unit_cost
            if enabled is not None:
                row.enabled = enabled
            if extra is not None:
                row.extra = dict(extra)
            await session.commit()
            await session.refresh(row)
            return _to_record(row)

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
