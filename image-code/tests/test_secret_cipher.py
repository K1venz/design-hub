"""RSA-OAEP secret encryption boundaries."""

import asyncio
from importlib.util import find_spec

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from design_hub.composition import build_secret_cipher
from design_hub.config.settings import Settings
from design_hub.infrastructure.security.rsa_secret_cipher import RsaSecretCipher
from design_hub.interface.api.asgi import create_production_app
from design_hub.interface.worker import run_worker

_DECRYPTION_ERROR = "敏感信息解密失败，请刷新页面后重试"


def _private_key_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


def test_generated_cipher_round_trips_arbitrary_utf8_secret() -> None:
    cipher = RsaSecretCipher.generate()

    assert cipher.decrypt(cipher.encrypt("密钥 with emoji 🔐")) == "密钥 with emoji 🔐"


@pytest.mark.parametrize("ciphertext", ["%%%not-base64%%%", "c2hvcnQ="])
def test_untrusted_ciphertext_uses_one_sanitized_error(ciphertext: str) -> None:
    cipher = RsaSecretCipher.generate()

    with pytest.raises(ValueError, match=f"^{_DECRYPTION_ERROR}$"):
        cipher.decrypt(ciphertext)


def test_persistent_pem_decrypts_ciphertext_across_instances() -> None:
    pem = _private_key_pem()
    encrypting_cipher = RsaSecretCipher.from_pem(pem)
    decrypting_cipher = RsaSecretCipher.from_pem(pem.replace("\n", "\\n"))

    assert decrypting_cipher.decrypt(encrypting_cipher.encrypt("跨实例 secret 🔐")) == (
        "跨实例 secret 🔐"
    )


def test_required_persistent_cipher_rejects_missing_private_key() -> None:
    settings = Settings(_env_file=None, require_persistent_secret_cipher=True)

    with pytest.raises(ValueError, match="AUTH_RSA_PRIVATE_KEY_PEM"):
        build_secret_cipher(settings)


@pytest.mark.parametrize("private_key_pem", ["", "not-a-private-key"])
def test_worker_fails_before_io_when_persistent_cipher_is_not_usable(
    private_key_pem: str,
) -> None:
    settings = Settings(
        _env_file=None,
        auth_rsa_private_key_pem=private_key_pem,
        require_persistent_secret_cipher=True,
    )

    with pytest.raises(ValueError):
        asyncio.run(run_worker(settings))


def test_api_fails_before_io_when_persistent_cipher_key_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REQUIRE_PERSISTENT_SECRET_CIPHER", "true")
    monkeypatch.setenv("AUTH_RSA_PRIVATE_KEY_PEM", "")

    with pytest.raises(ValueError, match="AUTH_RSA_PRIVATE_KEY_PEM"):
        with TestClient(create_production_app()):
            pass


def test_password_specific_cipher_modules_are_absent() -> None:
    assert find_spec("design_hub.ports.password_cipher") is None
    assert find_spec("design_hub.infrastructure.auth.rsa_cipher") is None
