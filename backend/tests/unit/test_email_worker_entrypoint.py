import asyncio
import ssl
from collections.abc import Callable
from typing import NoReturn

import aiosmtplib
import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncEngine

import studymate.email_worker as entrypoint
from studymate import bootstrap
from studymate.config import EmailWorkerSettings, SmtpDeliveryConfiguration
from studymate.infrastructure.email.smtp import SmtpConfiguration, SmtpEmailSender


def configuration(reply_to: str | None = None) -> EmailWorkerSettings:
    return EmailWorkerSettings(
        _env_file=None,
        database_url=SecretStr("postgresql+asyncpg://test:synthetic@127.0.0.1:1/worker_test"),
        code_key=SecretStr("01" * 32),
        envelope_key=SecretStr("02" * 32),
        observability=None,
        smtp=SmtpDeliveryConfiguration(
            hostname="smtp.example.test",
            port=587,
            username=SecretStr("synthetic"),
            password=SecretStr("synthetic"),
            sender="verify@example.test",
            reply_to=reply_to,
        ),
    )


async def test_worker_entrypoint_handles_stop_and_removes_signal_handlers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = configuration()
    registered: list[int] = []
    removed: list[int] = []
    loop = asyncio.get_running_loop()

    def add(signum: int, callback: Callable[[], object]) -> None:
        registered.append(signum)
        callback()

    def remove(signum: int) -> bool:
        removed.append(signum)
        return True

    def settings() -> EmailWorkerSettings:
        return current

    async def worker(value: EmailWorkerSettings, stop: asyncio.Event) -> None:
        assert value is current
        assert stop.is_set()

    monkeypatch.setattr(loop, "add_signal_handler", add)
    monkeypatch.setattr(loop, "remove_signal_handler", remove)
    monkeypatch.setattr(entrypoint, "EmailWorkerSettings", settings)
    monkeypatch.setattr(entrypoint, "run_email_worker", worker)
    await entrypoint.run()
    assert registered == removed


def test_worker_cli_owns_its_event_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    called = []
    configured: list[bool] = []

    async def run() -> None:
        called.append(True)

    monkeypatch.setattr(entrypoint, "run", run)
    monkeypatch.setattr(entrypoint, "configure_logging", lambda: configured.append(True))
    entrypoint.main()
    assert called == [True]
    assert configured == [True]


@pytest.mark.parametrize("reply_to", [None, "support@example.test"])
async def test_stopped_worker_propagates_optional_reply_header_without_database_or_smtp_io(
    monkeypatch: pytest.MonkeyPatch,
    reply_to: str | None,
) -> None:
    current = configuration(reply_to)
    captured: list[SmtpConfiguration] = []

    def no_database(*_args: object, **_kwargs: object) -> NoReturn:
        raise AssertionError("Stopped worker attempted a database connection")

    def sender(settings: SmtpConfiguration, tls: ssl.SSLContext) -> SmtpEmailSender:
        captured.append(settings)
        return SmtpEmailSender(settings, tls)

    async def no_smtp(*_args: object, **_kwargs: object) -> NoReturn:
        raise AssertionError("Stopped worker attempted SMTP delivery")

    monkeypatch.setattr(aiosmtplib, "send", no_smtp)
    monkeypatch.setattr(AsyncEngine, "connect", no_database)
    monkeypatch.setattr(bootstrap, "SmtpEmailSender", sender)
    stop = asyncio.Event()
    stop.set()
    await bootstrap.run_email_worker(current, stop)
    assert [item.reply_to for item in captured] == [reply_to]
    assert captured[0].sender == "verify@example.test"
