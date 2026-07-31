from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from design_hub.domain.enums import Role
from design_hub.domain.errors import AuthenticationError
from design_hub.domain.models import AuthUser
from design_hub.ports.auth import TokenService


class PyJwtTokenService(TokenService):
    """HS256 JWT 签发/校验（PyJWT）。密钥来自 settings（.env，不入库）。

    滑动续期（ISSUE-0058）：令牌签发超 renew_after_hours（半衰期）→ renew_if_stale 签新令牌。
    """

    def __init__(
        self,
        *,
        secret: str,
        ttl_hours: int = 24,
        renew_after_hours: int = 12,
        algorithm: str = "HS256",
    ) -> None:
        self._secret = secret
        self._ttl_hours = ttl_hours
        self._renew_after_hours = renew_after_hours
        self._algorithm = algorithm

    def issue(self, user: AuthUser) -> str:
        now = datetime.now(UTC)
        payload: dict[str, Any] = {
            "sub": user.user_id,
            "name": user.name,
            "role": user.role.value,
            "dept": user.dept,
            "iat": now,
            "exp": now + timedelta(hours=self._ttl_hours),
        }
        return jwt.encode(payload, self._secret, algorithm=self._algorithm)

    def verify(self, token: str) -> AuthUser:
        return self._to_user(self._decode(token))

    def renew_if_stale(self, token: str, current_user: AuthUser) -> str | None:
        payload = self._decode(token)  # exp 已过在此抛（正常路径 verify 已先拦）
        iat = datetime.fromtimestamp(int(payload["iat"]), UTC)
        if datetime.now(UTC) - iat < timedelta(hours=self._renew_after_hours):
            return None  # 未过半衰期，不续
        return self.issue(current_user)

    def _decode(self, token: str) -> dict[str, Any]:
        try:
            return jwt.decode(token, self._secret, algorithms=[self._algorithm])
        except jwt.PyJWTError as exc:  # 外部输入解析失败 → 翻译为领域错误(非吞错)
            raise AuthenticationError(f"令牌无效或已过期：{exc}") from exc

    @staticmethod
    def _to_user(payload: dict[str, Any]) -> AuthUser:
        return AuthUser(
            user_id=str(payload["sub"]),
            name=str(payload["name"]),
            role=Role(payload["role"]),
            dept=payload.get("dept"),
        )
