from abc import ABC, abstractmethod

from design_hub.domain.models import AuthUser


class TokenService(ABC):
    """JWT 签发/校验端口（DIP）。verify 失败抛 AuthenticationError（边界映射 401）。"""

    @abstractmethod
    def issue(self, user: AuthUser) -> str:
        ...

    @abstractmethod
    def verify(self, token: str) -> AuthUser:
        ...
