"""RSA-OAEP-SHA256 密码传输加密（ISSUE-0058）。

私钥留服务器（.env/文件 chmod600，不入库不入 git；qa/prod 各自生成）。
未配私钥（local/CI）则启动生成临时密钥对——每进程一把，本机联调/测试自足。
"""

import base64

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.serialization import load_pem_private_key

from design_hub.ports.password_cipher import PasswordCipher

# RSA-OAEP + MGF1(SHA-256) + SHA-256——与前端 WebCrypto RSA-OAEP(hash=SHA-256) 对齐
_OAEP = padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None)


class RsaPasswordCipher(PasswordCipher):
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

    def decrypt(self, ciphertext_b64: str) -> str:
        # 外部不可信输入：任何解码/解密失败统一翻译为 400 人话（不泄漏 crypto 细节、不 500）
        try:
            ciphertext = base64.b64decode(ciphertext_b64, validate=True)
            plaintext = self._private_key.decrypt(ciphertext, _OAEP)
            return plaintext.decode("utf-8")
        except Exception as exc:
            raise ValueError("密码解密失败，请刷新页面后重试") from exc

    def encrypt(self, plaintext: str) -> str:
        """公钥加密（前端职责；此处供本机/测试对拍，保证 OAEP 参数一致）。"""
        ciphertext = self._private_key.public_key().encrypt(plaintext.encode("utf-8"), _OAEP)
        return base64.b64encode(ciphertext).decode()

    @classmethod
    def generate(cls) -> "RsaPasswordCipher":
        return cls(rsa.generate_private_key(public_exponent=65537, key_size=2048))

    @classmethod
    def from_pem(cls, pem: str) -> "RsaPasswordCipher":
        key = load_pem_private_key(pem.encode(), password=None)
        if not isinstance(key, rsa.RSAPrivateKey):
            raise ValueError("AUTH_RSA_PRIVATE_KEY_PEM 不是 RSA 私钥")
        return cls(key)
