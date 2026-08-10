import asyncio
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import parseaddr, parsedate_to_datetime

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


def test_registration_verification_settings_have_secure_defaults_and_bounds() -> None:
    settings = Settings(_env_file=None)

    assert settings.registration_code_ttl_seconds == 600
    assert settings.registration_resend_cooldown_seconds == 60
    assert settings.registration_max_attempts == 5

    with pytest.raises(ValidationError):
        Settings(_env_file=None, registration_code_ttl_seconds=0)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, registration_resend_cooldown_seconds=601)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, registration_max_attempts=21)


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
        smtp_from_name="Design Hub",
        smtp_from="no-reply@example.com",
        smtp_use_tls=False,
        email_verification_code_pepper="pepper",
    )

    assert hasattr(composition, "build_mailer")
    assert isinstance(composition.build_mailer(settings), SmtpMailer)


@pytest.mark.parametrize(
    ("smtp_from_name", "smtp_from", "expected_error"),
    [
        (" \t ", "no-reply@example.com", "SMTP_FROM_NAME"),
        ("Design Hub", "not-an-email-address", "SMTP_FROM"),
        ("Design Hub", "@example.com", "SMTP_FROM"),
        ("Design Hub", "no reply@example.com", "SMTP_FROM"),
        (
            "Design Hub",
            "no-reply@example.com\r\nBcc: attacker@example.com",
            "SMTP_FROM",
        ),
    ],
)
def test_smtp_mode_rejects_invalid_sender_identity_before_mailer_construction(
    smtp_from_name: str,
    smtp_from: str,
    expected_error: str,
) -> None:
    with pytest.raises(ValidationError, match=expected_error):
        settings = Settings(
            _env_file=None,
            mail_delivery_mode="smtp",
            smtp_host="smtp",
            smtp_from_name=smtp_from_name,
            smtp_from=smtp_from,
            email_verification_code_pepper="pepper",
        )
        composition.build_mailer(settings)


def test_smtp_mailer_sets_complete_transactional_identity_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_messages: list[EmailMessage] = []

    class CapturingSmtp:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def __enter__(self) -> "CapturingSmtp":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def ehlo(self) -> None:
            return None

        def send_message(
            self,
            message: EmailMessage,
            *,
            from_addr: str,
            to_addrs: list[str],
        ) -> None:
            captured_messages.append(message)

    monkeypatch.setattr("design_hub.infrastructure.mail.smtp_mailer.smtplib.SMTP", CapturingSmtp)
    mailer = SmtpMailer(
        host="smtp",
        port=25,
        username="",
        password="",
        from_name="Design Hub",
        from_addr="no-reply@example.com",
        use_tls=False,
    )

    asyncio.run(mailer.send(to="first@example.com", subject="Verify", body_text="First"))
    asyncio.run(mailer.send(to="second@example.com", subject="Verify", body_text="Second"))

    parsed_messages = [
        BytesParser().parsebytes(message.as_bytes()) for message in captured_messages
    ]

    assert len(parsed_messages) == 2
    for message in parsed_messages:
        assert parseaddr(message["From"]) == ("Design Hub", "no-reply@example.com")
        assert parsedate_to_datetime(message["Date"]).utcoffset() is not None
        assert message["Auto-Submitted"] == "auto-generated"
        assert message["Message-ID"].endswith("@example.com>")
    assert parsed_messages[0]["Message-ID"] != parsed_messages[1]["Message-ID"]


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
