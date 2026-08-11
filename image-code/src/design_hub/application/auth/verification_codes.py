import hashlib
import hmac
from typing import Literal

VerificationCodePurpose = Literal["registration", "password-reset"]

_SUPPORTED_PURPOSES = frozenset(("registration", "password-reset"))


def digest_verification_code(
    *,
    purpose: VerificationCodePurpose,
    email: str,
    code: str,
    pepper: str,
) -> str:
    if purpose not in _SUPPORTED_PURPOSES:
        raise ValueError("unsupported verification code purpose")
    if not pepper.strip():
        raise ValueError("verification code pepper must not be blank")

    normalized_email = email.strip().lower()
    material = f"{purpose}:{normalized_email}:{code}".encode()
    return hmac.new(pepper.encode(), material, hashlib.sha256).hexdigest()
