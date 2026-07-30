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

    @abstractmethod
    def renew_if_stale(self, token: str, current_user: AuthUser) -> str | None:
        """滑动续期（ISSUE-0058）：已验证令牌若签发已过半衰期→签新令牌返回；未过→None。

        The caller supplies the current database identity so renewed claims never preserve a
        stale role or display name from the old token.
        """
        ...
