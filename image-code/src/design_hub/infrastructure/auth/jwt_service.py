from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from design_hub.domain.enums import Role
from design_hub.domain.errors import AuthenticationError
from design_hub.domain.models import AuthUser
from design_hub.ports.auth import TokenService


class PyJwtTokenService(TokenService):
    """HS256 JWT 签发/校验（PyJWT）。密钥来自 settings（.env，不入库）。"""

    def __init__(self, *, secret: str, ttl_hours: int = 24, algorithm: str = "HS256") -> None:
        self._secret = secret
        self._ttl_hours = ttl_hours
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
        try:
            payload = jwt.decode(token, self._secret, algorithms=[self._algorithm])
        except jwt.PyJWTError as exc:  # 外部输入解析失败 → 翻译为领域错误(非吞错)
            raise AuthenticationError(f"令牌无效或已过期：{exc}") from exc
        return AuthUser(
            user_id=str(payload["sub"]),
            name=str(payload["name"]),
            role=Role(payload["role"]),
            dept=payload.get("dept"),
        )
