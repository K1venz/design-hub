import asyncio
import json
from dataclasses import replace
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from design_hub.application.admin.model_config_service import ModelConfigService
from design_hub.domain.enums import ModelType, ProviderType
from design_hub.domain.errors import DomainError
from design_hub.domain.model_config import connection_fingerprint
from design_hub.infrastructure.db.base import Base
from design_hub.infrastructure.db.model_config_repo import SqlAlchemyModelConfigRepository
from design_hub.infrastructure.db.models import AdminAuditLogRow, GenerationItemRow, ListingJobRow
from design_hub.infrastructure.security.model_verification import PyJwtModelVerificationService
from design_hub.infrastructure.security.rsa_secret_cipher import RsaSecretCipher
from design_hub.interface.admin_schemas import ModelConfigOut
from design_hub.ports.model_config_repository import ModelConfigRecord

ACTOR_ID = 7


def test_gemini_native_image_requires_a_nonempty_key_pool() -> None:
    fingerprint = connection_fingerprint(
        model_type=ModelType.IMAGE,
        provider_type=ProviderType.GEMINI_NATIVE_IMAGE,
        base_url="https://api.example.test",
        upstream_model="gemini-3.1-flash-image",
        extra={},
        credentials_plaintext={"api_keys": ("key-a", "key-b")},
    )

    assert len(fingerprint) == 64
    with pytest.raises(ValueError, match="credential fields"):
        connection_fingerprint(
            model_type=ModelType.IMAGE,
            provider_type=ProviderType.GEMINI_NATIVE_IMAGE,
            base_url="https://api.example.test",
            upstream_model="gemini-3.1-flash-image",
            extra={},
            credentials_plaintext={"api_key": "wrong-shape"},
        )


async def _service() -> tuple[
    ModelConfigService, async_sessionmaker[AsyncSession], AsyncEngine, RsaSecretCipher
]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    cipher = RsaSecretCipher.generate()
    return (
        ModelConfigService(
            repo=SqlAlchemyModelConfigRepository(sessions),
            cipher=cipher,
            verifier=PyJwtModelVerificationService(
                secret="test-model-verification-secret-32-bytes", ttl_seconds=600
            ),
        ),
        sessions,
        engine,
        cipher,
    )


def _ciphertext(cipher: RsaSecretCipher, *, key: str = "image-key") -> dict[str, str | list[str]]:
    return {"standard_api_keys": [cipher.encrypt(key)]}


def _fingerprint(key: str = "image-key") -> str:
    return connection_fingerprint(
        model_type=ModelType.IMAGE,
        provider_type=ProviderType.OPENAI_COMPAT_IMAGE,
        base_url="https://images.example.test/v1",
        upstream_model="upstream-image",
        extra={"response_format": "b64_json"},
        credentials_plaintext={"standard_api_keys": (key,)},
    )


def _proof(service: ModelConfigService, fingerprint: str, *, name: str = "gpt-image") -> str:
    return service.verifier.issue(
        manager_id=str(ACTOR_ID), model_id=name, model_type=ModelType.IMAGE, fingerprint=fingerprint
    )


async def _create_active(
    service: ModelConfigService,
    cipher: RsaSecretCipher,
    *,
    name: str = "gpt-image",
    key: str = "image-key",
) -> None:
    await service.create(
        actor_id=ACTOR_ID,
        name=name,
        display_name="GPT Image",
        model_type=ModelType.IMAGE,
        provider_type=ProviderType.OPENAI_COMPAT_IMAGE,
        base_url="https://images.example.test/v1/",
        model="upstream-image",
        credentials=_ciphertext(cipher, key=key),
        unit_cost=Decimal("0.40"),
        enabled=True,
        extra={"response_format": "b64_json"},
        verification_proof=_proof(service, _fingerprint(key), name=name),
    )


def test_create_update_roundtrip_and_safe_output() -> None:
    async def run() -> None:
        service, _sessions, engine, cipher = await _service()
        try:
            await _create_active(service, cipher)
            saved = await service.update(
                actor_id=ACTOR_ID,
                name="gpt-image",
                display_name="Production GPT",
                unit_cost=Decimal("0.55"),
            )
            assert saved.display_name == "Production GPT"
            assert saved.base_url == "https://images.example.test/v1"
            assert saved.revision == 2
            assert saved.verified_at is not None
            output = ModelConfigOut.of(saved).model_dump(mode="json")
            assert output["credentials"] == {
                "has_credentials": True,
                "configured_fields": {"standard_api_keys": True},
            }
            serialized = json.dumps(output)
            assert "ciphertext" not in serialized and "image-key" not in serialized
            assert saved.verified_fingerprint not in serialized
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_create_proof_binds_to_canonical_persisted_connection() -> None:
    async def run() -> None:
        service, _sessions, engine, cipher = await _service()
        try:
            await service.create(
                actor_id=ACTOR_ID,
                name="  canonical-image  ",
                display_name="  Canonical image  ",
                model_type=ModelType.IMAGE,
                provider_type=ProviderType.OPENAI_COMPAT_IMAGE,
                base_url="  https://images.example.test/v1///  ",
                model="  canonical-upstream  ",
                credentials=_ciphertext(cipher),
                unit_cost=Decimal("0.40"),
                enabled=True,
                extra={"response_format": "b64_json"},
                verification_proof=_proof(
                    service,
                    connection_fingerprint(
                        model_type=ModelType.IMAGE,
                        provider_type=ProviderType.OPENAI_COMPAT_IMAGE,
                        base_url="https://images.example.test/v1",
                        upstream_model="canonical-upstream",
                        extra={"response_format": "b64_json"},
                        credentials_plaintext={"standard_api_keys": ("image-key",)},
                    ),
                    name="canonical-image",
                ),
            )
            saved = await service.repo.get("canonical-image")
            assert saved is not None
            assert saved.display_name == "Canonical image"
            assert saved.base_url == "https://images.example.test/v1"
            assert saved.model == "canonical-upstream"
            updated = await service.update(
                actor_id=ACTOR_ID,
                name="  canonical-image  ",
                base_url="  https://other.example.test/v1///  ",
                model="  next-upstream  ",
                verification_proof=_proof(
                    service,
                    connection_fingerprint(
                        model_type=ModelType.IMAGE,
                        provider_type=ProviderType.OPENAI_COMPAT_IMAGE,
                        base_url="https://other.example.test/v1",
                        upstream_model="next-upstream",
                        extra={"response_format": "b64_json"},
                        credentials_plaintext={"standard_api_keys": ("image-key",)},
                    ),
                    name="canonical-image",
                ),
            )
            assert updated.base_url == "https://other.example.test/v1"
            assert updated.model == "next-upstream"
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_connection_change_requires_exact_proof_and_replaces_or_retains_credentials() -> None:
    async def run() -> None:
        service, _sessions, engine, cipher = await _service()
        try:
            await _create_active(service, cipher)
            initial = await service.repo.get("gpt-image")
            assert initial is not None
            with pytest.raises(ValueError, match="invalid verification proof"):
                await service.update(
                    actor_id=ACTOR_ID,
                    name="gpt-image",
                    base_url="https://other.example.test/v1",
                    verification_proof="not-a-proof",
                )
            retained = await service.update(
                actor_id=ACTOR_ID,
                name="gpt-image",
                base_url="https://other.example.test/v1",
                verification_proof=_proof(
                    service,
                    connection_fingerprint(
                        model_type=ModelType.IMAGE,
                        provider_type=ProviderType.OPENAI_COMPAT_IMAGE,
                        base_url="https://other.example.test/v1",
                        upstream_model="upstream-image",
                        extra={"response_format": "b64_json"},
                        credentials_plaintext={"standard_api_keys": ("image-key",)},
                    ),
                ),
            )
            assert retained.credentials_ciphertext == initial.credentials_ciphertext
            assert retained.revision == 2 and retained.verified_at is not None
            replaced = await service.update(
                actor_id=ACTOR_ID,
                name="gpt-image",
                credentials=_ciphertext(cipher, key="replacement-key"),
                verification_proof=_proof(
                    service,
                    connection_fingerprint(
                        model_type=ModelType.IMAGE,
                        provider_type=ProviderType.OPENAI_COMPAT_IMAGE,
                        base_url="https://other.example.test/v1",
                        upstream_model="upstream-image",
                        extra={"response_format": "b64_json"},
                        credentials_plaintext={"standard_api_keys": ("replacement-key",)},
                    ),
                ),
            )
            assert replaced.revision == 3 and replaced.verified_at is not None
            assert replaced.credentials_ciphertext != retained.credentials_ciphertext
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_display_and_cost_updates_do_not_require_a_connection_proof() -> None:
    async def run() -> None:
        service, _sessions, engine, _cipher = await _service()
        try:
            await service.repo.create(
                actor_id=ACTOR_ID,
                record=ModelConfigRecord(
                    name="draft",
                    display_name="Draft",
                    model_type=ModelType.IMAGE,
                    provider_type=ProviderType.OPENAI_COMPAT_IMAGE,
                    base_url="",
                    model="",
                    credentials_ciphertext={},
                    unit_cost=Decimal("0"),
                    enabled=False,
                    revision=1,
                    verified_at=None,
                    verified_fingerprint=None,
                    extra={},
                ),
            )
            updated = await service.update(
                actor_id=ACTOR_ID,
                name="draft",
                display_name="Unconfigured draft",
                unit_cost=Decimal("0.10"),
            )
            assert updated.display_name == "Unconfigured draft"
            assert updated.unit_cost == Decimal("0.10")
            assert updated.revision == 2
            assert updated.verified_at is None
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_disabling_the_active_default_is_rejected() -> None:
    async def run() -> None:
        service, _sessions, engine, cipher = await _service()
        try:
            await _create_active(service, cipher)
            await service.set_default(actor_id=ACTOR_ID, name="gpt-image")
            with pytest.raises(DomainError, match="active default"):
                await service.update(actor_id=ACTOR_ID, name="gpt-image", enabled=False)
            catalog = await service.catalog(ModelType.IMAGE)
            assert catalog == [{"id": "gpt-image", "display_name": "GPT Image", "is_default": True}]
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_stale_revision_cannot_overwrite_a_verified_connection() -> None:
    async def run() -> None:
        service, _sessions, engine, cipher = await _service()
        try:
            await _create_active(service, cipher)
            stale = await service.repo.get("gpt-image")
            assert stale is not None
            await service.update(
                actor_id=ACTOR_ID,
                name="gpt-image",
                base_url="https://other.example.test/v1",
                verification_proof=_proof(
                    service,
                    connection_fingerprint(
                        model_type=ModelType.IMAGE,
                        provider_type=ProviderType.OPENAI_COMPAT_IMAGE,
                        base_url="https://other.example.test/v1",
                        upstream_model="upstream-image",
                        extra={"response_format": "b64_json"},
                        credentials_plaintext={"standard_api_keys": ("image-key",)},
                    ),
                ),
            )
            with pytest.raises(DomainError, match="revision conflict"):
                await service.repo.update(
                    actor_id=ACTOR_ID,
                    record=replace(
                        stale,
                        display_name="stale writer",
                        revision=stale.revision + 1,
                    ),
                    expected_revision=stale.revision,
                )
            current = await service.repo.get("gpt-image")
            assert current is not None
            assert current.base_url == "https://other.example.test/v1"
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_disabled_connection_still_needs_proof_and_enable_checks_stored_fingerprint() -> None:
    async def run() -> None:
        service, sessions, engine, cipher = await _service()
        try:
            with pytest.raises(ValueError, match="invalid verification proof"):
                await service.create(
                    actor_id=ACTOR_ID,
                    name="disabled",
                    display_name="Disabled",
                    model_type=ModelType.IMAGE,
                    provider_type=ProviderType.OPENAI_COMPAT_IMAGE,
                    base_url="https://images.example.test/v1",
                    model="upstream-image",
                    credentials=_ciphertext(cipher),
                    unit_cost=Decimal("0"),
                    enabled=False,
                    extra={"response_format": "b64_json"},
                    verification_proof="bad",
                )
            await _create_active(service, cipher)
            async with sessions() as session:
                async with session.begin():
                    row = await session.get(
                        __import__(
                            "design_hub.infrastructure.db.models", fromlist=["ModelConfig"]
                        ).ModelConfig,
                        "gpt-image",
                    )
                    assert row is not None
                    row.enabled = False
                    row.verified_fingerprint = "0" * 64
            with pytest.raises(ValueError, match="verified"):
                await service.update(actor_id=ACTOR_ID, name="gpt-image", enabled=True)
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_default_and_deletion_rules_are_transactional_and_secret_safe() -> None:
    async def run() -> None:
        service, sessions, engine, cipher = await _service()
        try:
            await _create_active(service, cipher, name="first")
            await _create_active(service, cipher, name="second")
            selected = await service.set_default(actor_id=ACTOR_ID, name="first")
            assert selected.name == "first"
            selected = await service.set_default(actor_id=ACTOR_ID, name="second")
            assert selected.name == "second"
            with pytest.raises(DomainError, match="default"):
                await service.delete(actor_id=ACTOR_ID, name="second")
            async with sessions() as session:
                async with session.begin():
                    session.add(
                        ListingJobRow(
                            id="job-1",
                            user_id="7",
                            idempotency_key="key",
                            request_fingerprint="fp",
                            prompt="p",
                            modifiers={},
                            ratio="1:1",
                            size="1x1",
                            n=1,
                            status="生成中",
                            total_cost=Decimal("0"),
                        )
                    )
                    session.add(
                        GenerationItemRow(
                            id="item-1",
                            job_id="job-1",
                            sequence=1,
                            render_tier="standard",
                            operation_type="generate_image",
                            final_prompt="p",
                            model="first",
                            ratio="1:1",
                            size="1x1",
                            seed=1,
                            reference_snapshot=[],
                            reserved_cost=Decimal("0"),
                            status="queued",
                            operation_id="operation-1",
                        )
                    )
            with pytest.raises(DomainError, match="active generation"):
                await service.delete(actor_id=ACTOR_ID, name="first")
            async with sessions() as session:
                rows = (await session.execute(select(AdminAuditLogRow))).scalars().all()
            snapshots = json.dumps([{"before": row.before, "after": row.after} for row in rows])
            assert "credentials_changed" in snapshots
            assert (
                "image-key" not in snapshots
                and "ciphertext" not in snapshots
                and _fingerprint() not in snapshots
            )
        finally:
            await engine.dispose()

    asyncio.run(run())
