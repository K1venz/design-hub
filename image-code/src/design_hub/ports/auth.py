from abc import ABC, abstractmethod

from design_hub.domain.models import AuthUser, OAuthProfile


class TokenService(ABC):
    """JWT 签发/校验端口（DIP）。verify 失败抛 AuthenticationError（边界映射 401）。"""

    @abstractmethod
    def issue(self, user: AuthUser) -> str:
        ...

    @abstractmethod
    def verify(self, token: str) -> AuthUser:
        ...


class OAuthClient(ABC):
    """OAuth 提供方端口（DIP）：code → 用户原始档案。

    真实实现走飞书/钉钉换 token + 拉部门（I/O 可重试）；mock 实现按约定本地返回。
    """

    @abstractmethod
    async def exchange(self, code: str) -> OAuthProfile:
        ...
