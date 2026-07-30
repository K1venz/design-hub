from abc import ABC, abstractmethod


class SecretCipher(ABC):
    """Public-key encryption boundary for application secrets."""

    @abstractmethod
    def public_key_pem(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def encrypt(self, plaintext: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def decrypt(self, ciphertext_b64: str) -> str:
        raise NotImplementedError
