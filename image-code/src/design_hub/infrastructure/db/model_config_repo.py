from __future__ import annotations

from typing import cast
from uuid import uuid4

from sqlalchemy import delete, exists, select
from sqlalchemy import update as sa_update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from design_hub.domain.admin import AdminAction
from design_hub.domain.enums import ModelType, ProviderType
from design_hub.domain.errors import DomainError, NotFoundError
from design_hub.domain.tasking import GenerationItemStatus, is_terminal
from design_hub.infrastructure.db.models import (
    AdminAuditLogRow,
    GenerationItemRow,
    ModelConfig,
    ModelDefault,
)
from design_hub.ports.model_config_repository import ModelConfigRecord, ModelConfigRepository


def _to_record(row: ModelConfig) -> ModelConfigRecord:
    credentials = _credentials_from_storage(row.credentials_ciphertext)
    return ModelConfigRecord(
        name=row.name,
        display_name=row.display_name,
        model_type=ModelType(row.model_type),
        provider_type=ProviderType(row.provider_type),
        base_url=row.base_url,
        model=row.model,
        credentials_ciphertext=credentials,
        unit_cost=row.unit_cost,
        enabled=row.enabled,
        revision=row.revision,
        verified_at=row.verified_at,
        verified_fingerprint=row.verified_fingerprint,
        extra=dict(row.extra),
    )


def _credentials_from_storage(values: dict[str, object]) -> dict[str, str | list[str]]:
    credentials: dict[str, str | list[str]] = {}
    for key, value in values.items():
        if isinstance(value, str):
            credentials[key] = value
        elif isinstance(value, list) and all(isinstance(item, str) for item in value):
            credentials[key] = list(value)
        else:
            raise DomainError("invalid stored credentials")
    return credentials


def _audit_snapshot(row: ModelConfig, *, credentials_changed: bool = False) -> dict[str, object]:
    return {
        "name": row.name,
        "display_name": row.display_name,
        "model_type": row.model_type,
        "provider_type": row.provider_type,
        "base_url": row.base_url,
        "model": row.model,
        "unit_cost": str(row.unit_cost),
        "enabled": row.enabled,
        "revision": row.revision,
        "verified": row.verified_at is not None,
        "extra": dict(row.extra),
        "credentials_changed": credentials_changed,
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
                (await session.execute(select(ModelConfig).order_by(ModelConfig.name)))
                .scalars()
                .all()
            )
            return [_to_record(row) for row in rows]

    async def get(self, name: str) -> ModelConfigRecord | None:
        async with self._session_factory() as session:
            row = await session.get(ModelConfig, name)
            return _to_record(row) if row is not None else None

    async def get_default(self, model_type: ModelType) -> str | None:
        async with self._session_factory() as session:
            return cast(
                str | None,
                await session.scalar(
                    select(ModelDefault.model_name).where(
                        ModelDefault.model_type == model_type.value
                    )
                ),
            )

    async def create(self, *, actor_id: int, record: ModelConfigRecord) -> ModelConfigRecord:
        async with self._session_factory() as session:
            async with session.begin():
                if await session.get(ModelConfig, record.name) is not None:
                    raise DomainError("model config already exists")
                row = ModelConfig(
                    name=record.name,
                    display_name=record.display_name,
                    model_type=record.model_type.value,
                    provider_type=record.provider_type.value,
                    base_url=record.base_url,
                    model=record.model,
                    credentials_ciphertext=dict(record.credentials_ciphertext),
                    unit_cost=record.unit_cost,
                    enabled=record.enabled,
                    revision=record.revision,
                    verified_at=record.verified_at,
                    verified_fingerprint=record.verified_fingerprint,
                    extra=record.extra,
                )
                session.add(row)
                _audit(
                    session,
                    actor_id=actor_id,
                    action=AdminAction.MODEL_CREATE,
                    name=record.name,
                    before=None,
                    after=_audit_snapshot(row, credentials_changed=True),
                )
                await session.flush()
                return _to_record(row)

    async def update(
        self,
        *,
        actor_id: int,
        record: ModelConfigRecord,
        expected_revision: int,
    ) -> ModelConfigRecord:
        if record.revision != expected_revision + 1:
            raise ValueError("invalid model revision")
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.get(ModelConfig, record.name)
                if row is None:
                    raise NotFoundError("model config not found")
                before = _audit_snapshot(row)
                credentials_changed = row.credentials_ciphertext != record.credentials_ciphertext
                statement = sa_update(ModelConfig).where(
                    ModelConfig.name == record.name,
                    ModelConfig.revision == expected_revision,
                )
                if not record.enabled:
                    statement = statement.where(
                        ~exists(
                            select(ModelDefault.model_type).where(
                                ModelDefault.model_type == record.model_type.value,
                                ModelDefault.model_name == record.name,
                            )
                        )
                    )
                result = cast(
                    CursorResult[object],
                    await session.execute(
                        statement.values(
                            display_name=record.display_name,
                            model_type=record.model_type.value,
                            provider_type=record.provider_type.value,
                            base_url=record.base_url,
                            model=record.model,
                            credentials_ciphertext=dict(record.credentials_ciphertext),
                            unit_cost=record.unit_cost,
                            enabled=record.enabled,
                            revision=record.revision,
                            verified_at=record.verified_at,
                            verified_fingerprint=record.verified_fingerprint,
                            extra=record.extra,
                        )
                    ),
                )
                if result.rowcount != 1:
                    default_name = await session.scalar(
                        select(ModelDefault.model_name).where(
                            ModelDefault.model_type == record.model_type.value,
                            ModelDefault.model_name == record.name,
                        )
                    )
                    if not record.enabled and default_name == record.name:
                        raise DomainError("cannot disable active default model")
                    raise DomainError("model config revision conflict")
                await session.refresh(row)
                _audit(
                    session,
                    actor_id=actor_id,
                    action=AdminAction.MODEL_UPDATE,
                    name=record.name,
                    before=before,
                    after=_audit_snapshot(row, credentials_changed=credentials_changed),
                )
                await session.flush()
                return _to_record(row)

    async def delete(self, *, actor_id: int, name: str) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.get(ModelConfig, name)
                if row is None:
                    raise NotFoundError("model config not found")
                no_active_default = ~exists(
                    select(ModelDefault.model_type).where(
                        ModelDefault.model_type == row.model_type,
                        ModelDefault.model_name == name,
                    )
                )
                terminal_statuses = tuple(
                    status.value for status in GenerationItemStatus if is_terminal(status)
                )
                no_active_generation = ~exists(
                    select(GenerationItemRow.id).where(
                        GenerationItemRow.model == name,
                        GenerationItemRow.status.not_in(terminal_statuses),
                    )
                )
                result = cast(
                    CursorResult[object],
                    await session.execute(
                        delete(ModelConfig).where(
                            ModelConfig.name == name,
                            no_active_default,
                            no_active_generation,
                        )
                    ),
                )
                if result.rowcount != 1:
                    default_name = await session.scalar(
                        select(ModelDefault.model_name).where(
                            ModelDefault.model_type == row.model_type,
                            ModelDefault.model_name == name,
                        )
                    )
                    if default_name == name:
                        raise DomainError("cannot delete active default model")
                    active_generation = await session.scalar(
                        select(GenerationItemRow.id).where(
                            GenerationItemRow.model == name,
                            GenerationItemRow.status.not_in(terminal_statuses),
                        )
                    )
                    if active_generation is not None:
                        raise DomainError("cannot delete model referenced by active generation")
                    raise NotFoundError("model config not found")
                _audit(
                    session,
                    actor_id=actor_id,
                    action=AdminAction.MODEL_DELETE,
                    name=name,
                    before=_audit_snapshot(row),
                    after=None,
                )

    async def set_default(self, *, actor_id: int, name: str) -> ModelConfigRecord:
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.get(ModelConfig, name, with_for_update=True)
                if row is None:
                    raise NotFoundError("model config not found")
                if not row.enabled or row.verified_at is None or row.verified_fingerprint is None:
                    raise DomainError("default model must be enabled and verified")
                before = _audit_snapshot(row)
                default = await session.get(ModelDefault, row.model_type, with_for_update=True)
                if default is None:
                    session.add(ModelDefault(model_type=row.model_type, model_name=row.name))
                else:
                    default.model_name = row.name
                _audit(
                    session,
                    actor_id=actor_id,
                    action=AdminAction.MODEL_DEFAULT_SET,
                    name=name,
                    before=before,
                    after=_audit_snapshot(row),
                )
                await session.flush()
                return _to_record(row)
