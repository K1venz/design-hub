import asyncio
from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from design_hub.application.admin.model_config_service import ModelConfigService
from design_hub.domain.enums import ModelType, ProviderType, Role
from design_hub.domain.model_config import connection_fingerprint
from design_hub.domain.models import AuthUser
from design_hub.infrastructure.db.base import Base
from design_hub.infrastructure.db.model_config_repo import SqlAlchemyModelConfigRepository
from design_hub.infrastructure.security.model_verification import PyJwtModelVerificationService
from design_hub.infrastructure.security.rsa_secret_cipher import RsaSecretCipher
from design_hub.interface.api.app import register_error_handlers
from design_hub.interface.api.deps import get_current_user
from design_hub.interface.api.routes import models


def test_image_catalog_exposes_only_active_verified_models() -> None:
    async def run() -> tuple[ModelConfigService, object]:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        cipher = RsaSecretCipher.generate()
        service = ModelConfigService(
            repo=SqlAlchemyModelConfigRepository(sessions),
            cipher=cipher,
            verifier=PyJwtModelVerificationService(
                secret="test-model-verification-secret-32-bytes", ttl_seconds=600
            ),
        )
        plaintext = "catalog-key"
        fingerprint = connection_fingerprint(
            model_type=ModelType.IMAGE,
            provider_type=ProviderType.OPENAI_COMPAT_IMAGE,
            base_url="https://images.example.test/v1",
            upstream_model="upstream-image",
            extra={},
            credentials_plaintext={"standard_api_keys": (plaintext,)},
        )
        await service.create(
            actor_id=7,
            name="gpt-image-2",
            display_name="GPT Image 2.0",
            model_type=ModelType.IMAGE,
            provider_type=ProviderType.OPENAI_COMPAT_IMAGE,
            base_url="https://images.example.test/v1",
            model="upstream-image",
            credentials={"standard_api_keys": [cipher.encrypt(plaintext)]},
            unit_cost=Decimal("0.4"),
            enabled=True,
            extra={},
            verification_proof=service.verifier.issue(
                manager_id="7",
                model_id="gpt-image-2",
                model_type=ModelType.IMAGE,
                fingerprint=fingerprint,
            ),
        )
        await service.set_default(actor_id=7, name="gpt-image-2")

        nano_plaintext = "nano-catalog-key"
        nano_fingerprint = connection_fingerprint(
            model_type=ModelType.IMAGE,
            provider_type=ProviderType.GEMINI_NATIVE_IMAGE,
            base_url="https://gemini.example.test",
            upstream_model="gemini-3.1-flash-image",
            extra={},
            credentials_plaintext={"api_keys": (nano_plaintext,)},
        )
        await service.create(
            actor_id=7,
            name="nano-banana-2",
            display_name="Nano Banana 2",
            model_type=ModelType.IMAGE,
            provider_type=ProviderType.GEMINI_NATIVE_IMAGE,
            base_url="https://gemini.example.test",
            model="gemini-3.1-flash-image",
            credentials={"api_keys": [cipher.encrypt(nano_plaintext)]},
            unit_cost=Decimal("0.1"),
            enabled=True,
            extra={},
            verification_proof=service.verifier.issue(
                manager_id="7",
                model_id="nano-banana-2",
                model_type=ModelType.IMAGE,
                fingerprint=nano_fingerprint,
            ),
        )

        chat_plaintext = "chat-catalog-key"
        chat_fingerprint = connection_fingerprint(
            model_type=ModelType.CHAT,
            provider_type=ProviderType.OPENAI_COMPAT_CHAT,
            base_url="https://chat.example.test/v1",
            upstream_model="upstream-chat",
            extra={},
            credentials_plaintext={"api_key": chat_plaintext},
        )
        await service.create(
            actor_id=7,
            name="chat-active",
            display_name="Chat Active",
            model_type=ModelType.CHAT,
            provider_type=ProviderType.OPENAI_COMPAT_CHAT,
            base_url="https://chat.example.test/v1",
            model="upstream-chat",
            credentials={"api_key": cipher.encrypt(chat_plaintext)},
            unit_cost=Decimal("0.2"),
            enabled=True,
            extra={},
            verification_proof=service.verifier.issue(
                manager_id="7",
                model_id="chat-active",
                model_type=ModelType.CHAT,
                fingerprint=chat_fingerprint,
            ),
        )
        await service.set_default(actor_id=7, name="chat-active")
        return service, engine

    service, engine = asyncio.run(run())
    try:
        image_catalog = asyncio.run(service.catalog(ModelType.IMAGE))
        assert [item["id"] for item in image_catalog] == [
            "gpt-image-2",
            "nano-banana-2",
        ]
        gpt_capabilities = image_catalog[0]["image_capabilities"]
        nano_capabilities = image_catalog[1]["image_capabilities"]
        assert isinstance(gpt_capabilities, dict)
        assert isinstance(nano_capabilities, dict)
        assert [tier["id"] for tier in gpt_capabilities["render_tiers"]] == [
            "standard",
            "4k",
        ]
        assert [tier["id"] for tier in nano_capabilities["render_tiers"]] == [
            "standard",
            "2k",
            "4k",
        ]
        assert nano_capabilities["render_tiers"][1]["ratios"] == [
            "1:1", "1:4", "1:8", "2:3", "3:2", "3:4", "4:1",
            "4:3", "4:5", "5:4", "8:1", "9:16", "16:9", "21:9",
        ]
        assert asyncio.run(service.catalog(ModelType.CHAT)) == [
            {
                "id": "chat-active",
                "display_name": "Chat Active",
                "is_default": True,
            }
        ]
        app = FastAPI()
        register_error_handlers(app)
        app.state.model_config_service = service
        app.include_router(models.router)
        client = TestClient(app)
        assert client.get("/models/image").status_code == 401
        app.dependency_overrides[get_current_user] = lambda: AuthUser(
            user_id="1", name="Designer", role=Role.DESIGNER, dept=None
        )
        response = client.get("/models/image")
        assert response.status_code == 200
        image_json = response.json()
        assert [item["id"] for item in image_json] == [
            "gpt-image-2",
            "nano-banana-2",
        ]
        assert image_json[1]["image_capabilities"]["render_tiers"][1] == {
            "id": "2k",
            "label": "2K 高清",
            "ratios": [
                "1:1", "1:4", "1:8", "2:3", "3:2", "3:4", "4:1",
                "4:3", "4:5", "5:4", "8:1", "9:16", "16:9", "21:9",
            ],
        }
        assert "unit_cost" not in response.text
        assert "base_url" not in response.text
        assert "catalog-key" not in response.text

        chat_response = client.get("/models/chat")
        assert chat_response.status_code == 200
        assert chat_response.json() == [
            {
                "id": "chat-active",
                "display_name": "Chat Active",
                "is_default": True,
            }
        ]
        assert "unit_cost" not in chat_response.text
        assert "base_url" not in chat_response.text
        assert "chat-catalog-key" not in chat_response.text
    finally:
        asyncio.run(engine.dispose())
