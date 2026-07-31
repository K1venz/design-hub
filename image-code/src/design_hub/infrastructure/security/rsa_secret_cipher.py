"""RSA-OAEP secret cipher implementation."""

import base64

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.serialization import load_pem_private_key

from design_hub.ports.secret_cipher import SecretCipher

_DECRYPTION_ERROR = "敏感信息解密失败，请刷新页面后重试"
_RSA_KEY_SIZE = 2048
_OAEP = padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None)


class RsaSecretCipher(SecretCipher):
    def __init__(self, private_key: rsa.RSAPrivateKey) -> None:
        self._private_key = private_key
        self._public_pem = (
            private_key.public_key()
            .public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            .decode()
        )

    def public_key_pem(self) -> str:
        return self._public_pem

    def encrypt(self, plaintext: str) -> str:
        ciphertext = self._private_key.public_key().encrypt(plaintext.encode("utf-8"), _OAEP)
        return base64.b64encode(ciphertext).decode()

    def decrypt(self, ciphertext_b64: str) -> str:
        try:
            ciphertext = base64.b64decode(ciphertext_b64, validate=True)
            return self._private_key.decrypt(ciphertext, _OAEP).decode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ValueError(_DECRYPTION_ERROR) from exc

    @classmethod
    def generate(cls) -> "RsaSecretCipher":
        return cls(rsa.generate_private_key(public_exponent=65537, key_size=_RSA_KEY_SIZE))

    @classmethod
    def from_pem(cls, pem: str) -> "RsaSecretCipher":
        key = load_pem_private_key(pem.replace("\\n", "\n").encode(), password=None)
        if not isinstance(key, rsa.RSAPrivateKey):
            raise ValueError("AUTH_RSA_PRIVATE_KEY_PEM 不是 RSA 私钥")
        if key.key_size != _RSA_KEY_SIZE:
            raise ValueError(f"AUTH_RSA_PRIVATE_KEY_PEM 必须是 {_RSA_KEY_SIZE} 位 RSA 私钥")
        return cls(key)
