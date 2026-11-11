import asyncio
from collections.abc import Callable
from typing import NoReturn

import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy.ext.asyncio import AsyncEngine

import studymate.changes_worker as entrypoint
from studymate.bootstrap import run_changes_worker
from studymate.config import ChangesWorkerSettings


def configuration() -> ChangesWorkerSettings:
    return ChangesWorkerSettings(
        _env_file=None,
        database_url=SecretStr("postgresql+asyncpg://test:synthetic@127.0.0.1:1/changes_test"),
        observability=None,
    )


async def test_stopped_changes_worker_composes_without_database_auth_or_external_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def deny_database(*_args: object, **_kwargs: object) -> NoReturn:
        raise AssertionError("Stopped changes worker attempted database access")

    monkeypatch.setattr(AsyncEngine, "connect", deny_database)
    current = configuration()
    assert set(type(current).model_fields) == {"database_url", "observability"}
    stop = asyncio.Event()
    stop.set()
    await run_changes_worker(current, stop)


async def test_changes_cli_removes_both_signal_handlers_after_stop(
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

    async def run_worker(value: ChangesWorkerSettings, stop: asyncio.Event) -> None:
        assert value is current
        assert stop.is_set()

    monkeypatch.setattr(loop, "add_signal_handler", add)
    monkeypatch.setattr(loop, "remove_signal_handler", remove)
    monkeypatch.setattr(entrypoint, "ChangesWorkerSettings", lambda: current)
    monkeypatch.setattr(entrypoint, "run_changes_worker", run_worker)
    await entrypoint.run()
    assert registered == removed


def test_changes_cli_owns_safe_logging_and_event_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    async def run() -> None:
        calls.append("run")

    monkeypatch.setattr(entrypoint, "run", run)
    monkeypatch.setattr(entrypoint, "configure_logging", lambda: calls.append("logging"))
    entrypoint.main()
    assert calls == ["logging", "run"]


def test_changes_worker_rejects_non_async_database_without_credentials_in_errors() -> None:
    with pytest.raises(ValidationError, match="asyncpg") as error:
        ChangesWorkerSettings(
            _env_file=None,
            database_url=SecretStr("postgresql://test:synthetic-private@localhost/changes"),
        )
    assert "synthetic-private" not in str(error.value)
