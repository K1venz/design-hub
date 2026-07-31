from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from design_hub.domain.enums import ModelType
from design_hub.ports.model_verification import ModelVerificationService

_AUDIENCE = "model-config-verification"
_INVALID_PROOF_MESSAGE = "invalid verification proof"


class PyJwtModelVerificationService(ModelVerificationService):
    """HS256 issuer for short-lived, exact-connection verification proofs."""

    def __init__(self, *, secret: str, ttl_seconds: int) -> None:
        if not secret or ttl_seconds <= 0:
            raise ValueError("invalid model verification configuration")
        self._secret = secret
        self._ttl_seconds = ttl_seconds

    def issue(
        self,
        *,
        manager_id: str,
        model_id: str,
        model_type: ModelType,
        fingerprint: str,
    ) -> str:
        payload: dict[str, Any] = {
            "aud": _AUDIENCE,
            "exp": datetime.now(UTC) + timedelta(seconds=self._ttl_seconds),
            "fingerprint": fingerprint,
            "manager_id": manager_id,
            "model_id": model_id,
            "model_type": model_type.value,
        }
        return jwt.encode(payload, self._secret, algorithm="HS256")

    def verify(
        self,
        proof: str,
        *,
        manager_id: str,
        model_id: str,
        model_type: ModelType,
        fingerprint: str,
    ) -> None:
        try:
            payload = jwt.decode(
                proof,
                self._secret,
                algorithms=["HS256"],
                audience=_AUDIENCE,
            )
        except jwt.PyJWTError as exc:
            raise ValueError(_INVALID_PROOF_MESSAGE) from exc
        if (
            payload.get("manager_id") != manager_id
            or payload.get("model_id") != model_id
            or payload.get("model_type") != model_type.value
            or payload.get("fingerprint") != fingerprint
        ):
            raise ValueError(_INVALID_PROOF_MESSAGE)
