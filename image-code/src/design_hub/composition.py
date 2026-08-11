"""组装根（Composition Root）：唯一允许同时认识 application 与 infrastructure 的地方。

DIP 的落点——把抽象端口绑定到具体适配器都集中在此，其余各层只见抽象。
2026-06-09 旧海报/项目出图流下线（ISSUE-0039）后，仅保留 listing 主线所需的装配
（测试 registry / 图床签名 / 上传落点）。
"""

from collections.abc import Mapping
from decimal import Decimal

from design_hub.application.registry import ProviderRegistry
from design_hub.config.settings import Settings
from design_hub.infrastructure.mail import LoggingMailer, SmtpMailer
from design_hub.infrastructure.providers.mock import MockModelProvider
from design_hub.infrastructure.security.rsa_secret_cipher import RsaSecretCipher
from design_hub.infrastructure.storage.local import LocalImageStore, LocalMediaUrlSigner
from design_hub.infrastructure.storage.local_upload import LocalUploadStore
from design_hub.infrastructure.storage.tos import (
    TosImageStore,
    TosMediaUrlSigner,
    TosUploadStore,
    build_tos_client,
)
from design_hub.ports.image_store import ImageStore
from design_hub.ports.mail import MailPort
from design_hub.ports.media_url_signer import MediaUrlSigner
from design_hub.ports.secret_cipher import SecretCipher
from design_hub.ports.upload_store import UploadStore

_MOCK_UNIT_COSTS: dict[str, Decimal] = {
    "seedream-5": Decimal("0.20"),
    "gpt-image-2": Decimal("0.05"),
    "wanxiang-2.7-pro": Decimal("0.05"),
    "lingdong-2": Decimal("0.04"),
}


def build_mock_registry(
    unit_costs: Mapping[str, Decimal] | None = None,
) -> ProviderRegistry:
    """Build an explicit isolated-test registry; production never selects it."""
    costs = {**_MOCK_UNIT_COSTS, **(unit_costs or {})}
    registry = ProviderRegistry()
    for name, unit_cost in costs.items():
        registry.register(MockModelProvider(name=name, unit_cost=unit_cost))
    return registry


def _tos_enabled(settings: Settings) -> bool:
    return bool(
        settings.tos_access_key.get_secret_value()
        and settings.tos_generate_bucket
        and settings.tos_upload_bucket
    )


def build_media_signer(settings: Settings) -> MediaUrlSigner:
    """配了 TOS → 预签名 url 签名器；否则本地静态拼接（nginx /img，ISSUE-0029）。"""
    if _tos_enabled(settings):
        return TosMediaUrlSigner(
            build_tos_client(settings),
            settings.tos_generate_bucket,
            settings.tos_upload_bucket,
            settings.tos_signed_url_ttl,
        )
    return LocalMediaUrlSigner(settings.image_public_base_url)


def build_image_store(settings: Settings) -> ImageStore:
    """出图结果落点：配了 TOS → generate 桶；否则本地目录。"""
    if _tos_enabled(settings):
        return TosImageStore(
            build_tos_client(settings),
            settings.tos_generate_bucket,
            build_media_signer(settings),
        )
    return LocalImageStore(
        settings.image_output_dir, public_base_url=settings.image_public_base_url
    )


def build_upload_store(settings: Settings) -> UploadStore:
    """上传图落点：配了 TOS → upload 桶；否则本地 assets/ 目录。"""
    if _tos_enabled(settings):
        return TosUploadStore(build_tos_client(settings), settings.tos_upload_bucket)
    return LocalUploadStore(settings.asset_output_dir)


def build_secret_cipher(settings: Settings) -> SecretCipher:
    """Build the RSA-OAEP cipher for all application secrets."""
    pem = settings.auth_rsa_private_key_pem.get_secret_value()
    if pem:
        return RsaSecretCipher.from_pem(pem)
    if settings.require_persistent_secret_cipher:
        raise ValueError("AUTH_RSA_PRIVATE_KEY_PEM is required for persistent secret encryption")
    return RsaSecretCipher.generate()


def build_mailer(settings: Settings) -> MailPort:
    """Bind the explicitly selected outbound mail adapter."""
    if settings.mail_delivery_mode == "log":
        return LoggingMailer()
    return SmtpMailer(
        host=settings.smtp_host.strip(),
        port=settings.smtp_port,
        username=settings.smtp_username,
        password=settings.smtp_password.get_secret_value(),
        from_name=settings.smtp_from_name.strip(),
        from_addr=settings.smtp_from.strip(),
        use_tls=settings.smtp_use_tls,
    )
