import asyncio

import pytest
from pydantic import SecretStr, ValidationError

from studymate.bootstrap import run_email_worker
from studymate.config import EmailWorkerSettings, SmtpDeliveryConfiguration


def configuration() -> EmailWorkerSettings:
    return EmailWorkerSettings(
        _env_file=None,
        database_url=SecretStr("postgresql+asyncpg://test:synthetic@127.0.0.1:1/worker_test"),
        code_key=SecretStr("01" * 32),
        envelope_key=SecretStr("02" * 32),
        smtp=SmtpDeliveryConfiguration(
            hostname="smtp.example.test",
            port=587,
            username=SecretStr("synthetic-user"),
            password=SecretStr("synthetic-password"),
            sender="verify@example.test",
        ),
    )


async def test_stopped_worker_composes_and_closes_without_google_or_smtp_access() -> None:
    settings = configuration()
    assert "synthetic-password" not in repr(settings)
    assert "client_secret" not in type(settings).model_fields
    stop = asyncio.Event()
    stop.set()
    await run_email_worker(settings, stop)


@pytest.mark.parametrize(("username", "password"), [("", "synthetic"), ("synthetic", "")])
def test_smtp_credentials_are_explicit(username: str, password: str) -> None:
    with pytest.raises(ValidationError, match="credentials"):
        SmtpDeliveryConfiguration(
            hostname="smtp.example.test",
            port=587,
            username=SecretStr(username),
            password=SecretStr(password),
            sender="verify@example.test",
        )


def test_worker_rejects_shared_crypto_keys() -> None:
    current = configuration()
    with pytest.raises(ValidationError, match="distinct"):
        EmailWorkerSettings(
            database_url=current.database_url,
            code_key=current.code_key,
            envelope_key=current.code_key,
            smtp=current.smtp,
            _env_file=None,
        )
