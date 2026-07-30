"""RSA-OAEP secret encryption boundaries."""

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from design_hub.composition import build_secret_cipher
from design_hub.config.settings import Settings
from design_hub.infrastructure.security.rsa_secret_cipher import RsaSecretCipher

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
