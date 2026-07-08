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
    def renew_if_stale(self, token: str) -> str | None:
        """滑动续期（ISSUE-0058）：已验证令牌若签发已过半衰期→签新令牌返回；未过→None。

        exp 已过的令牌由 verify 先拦（401，不到这）；调用方（鉴权依赖）在 verify 成功后调本方法，
        非 None 即放响应头 X-Renewed-Token。幂等：并发多请求各自续、无害。
        """
        ...
