from abc import ABC, abstractmethod


class PasswordCipher(ABC):
    """密码传输加密端口（ISSUE-0058）：前端用公钥 RSA-OAEP-SHA256 加密密码、服务端私钥解密。

    纵深防御——挡被动嗅探/日志泄漏/自签证书场景偷看；不挡全能主动 MITM（根治=正式域名+LE 证书）。
    存储侧 bcrypt 不变；本端口只处理「传输密文 → 明文」这一段。
    """

    @abstractmethod
    def public_key_pem(self) -> str:
        """SPKI 公钥 PEM（公开、可缓存），供前端 WebCrypto importKey。"""
        ...

    @abstractmethod
    def decrypt(self, ciphertext_b64: str) -> str:
        """base64(RSA-OAEP-SHA256 密文) → 明文密码。失败抛 ValueError（边界映射 400）。"""
        ...
