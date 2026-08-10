import pytest

from design_hub.application.auth.verification_codes import digest_verification_code


def test_digest_normalizes_email_and_matches_hmac_sha256() -> None:
    digest = digest_verification_code(
        purpose="password-reset",
        email=" Alice@Example.COM ",
        code="123456",
        pepper="pepper",
    )

    assert digest == "96733ebd8ad4ad4066dce067c6ed8ded7d13513a7b6a4652df6bb3826b6cb9e7"
    assert digest == digest_verification_code(
        purpose="password-reset",
        email="alice@example.com",
        code="123456",
        pepper="pepper",
    )


def test_digest_separates_verification_code_purposes() -> None:
    registration = digest_verification_code(
        purpose="registration",
        email="alice@example.com",
        code="123456",
        pepper="pepper",
    )
    password_reset = digest_verification_code(
        purpose="password-reset",
        email="alice@example.com",
        code="123456",
        pepper="pepper",
    )

    assert registration != password_reset


def test_digest_rejects_blank_pepper() -> None:
    with pytest.raises(ValueError, match="pepper"):
        digest_verification_code(
            purpose="registration",
            email="alice@example.com",
            code="123456",
            pepper=" ",
        )


def test_digest_rejects_unsupported_purpose() -> None:
    with pytest.raises(ValueError, match="purpose"):
        digest_verification_code(
            purpose="email-change",  # type: ignore[arg-type]
            email="alice@example.com",
            code="123456",
            pepper="pepper",
        )
