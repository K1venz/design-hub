import asyncio

import pytest
from pydantic import ValidationError
from structlog.testing import capture_logs

from design_hub import composition
from design_hub.config.settings import Settings
from design_hub.infrastructure.mail import LoggingMailer, SmtpMailer


def test_smtp_mode_rejects_missing_delivery_settings() -> None:
    with pytest.raises(ValidationError, match="SMTP_HOST"):
        Settings(_env_file=None, mail_delivery_mode="smtp")


def test_smtp_mode_requires_email_verification_code_pepper() -> None:
    with pytest.raises(ValidationError, match="EMAIL_VERIFICATION_CODE_PEPPER"):
        Settings(
            _env_file=None,
            mail_delivery_mode="smtp",
            smtp_host="smtp",
            smtp_from="no-reply@example.com",
        )


def test_smtp_mode_rejects_blank_email_verification_code_pepper() -> None:
    with pytest.raises(ValidationError, match="EMAIL_VERIFICATION_CODE_PEPPER"):
        Settings(
            _env_file=None,
            mail_delivery_mode="smtp",
            smtp_host="smtp",
            smtp_from="no-reply@example.com",
            email_verification_code_pepper=" \t ",
        )


def test_legacy_reset_pepper_env_does_not_configure_smtp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PASSWORD_RESET_CODE_PEPPER", "legacy-pepper")

    with pytest.raises(ValidationError, match="EMAIL_VERIFICATION_CODE_PEPPER"):
        Settings(
            _env_file=None,
            mail_delivery_mode="smtp",
            smtp_host="smtp",
            smtp_from="no-reply@example.com",
        )


def test_smtp_mode_builds_network_mailer() -> None:
    settings = Settings(
        _env_file=None,
        mail_delivery_mode="smtp",
        smtp_host="smtp",
        smtp_port=25,
        smtp_from="no-reply@example.com",
        smtp_use_tls=False,
        email_verification_code_pepper="pepper",
    )

    assert hasattr(composition, "build_mailer")
    assert isinstance(composition.build_mailer(settings), SmtpMailer)


def test_log_mode_does_not_expose_message_body() -> None:
    with capture_logs() as logs:
        asyncio.run(
            LoggingMailer().send(
                to="user@example.com",
                subject="reset",
                body_text="验证码：123456",
            )
        )

    assert "123456" not in repr(logs)
