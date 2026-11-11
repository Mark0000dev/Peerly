import asyncio
from collections.abc import Callable
from typing import NoReturn
from uuid import uuid4

import pytest
from aiobotocore.client import AioBaseClient
from pydantic import SecretStr, ValidationError
from sqlalchemy.ext.asyncio import AsyncEngine

import studymate.media_worker as entrypoint
from studymate.bootstrap import run_media_worker
from studymate.config import MediaConfiguration, MediaWorkerSettings


def configuration() -> MediaWorkerSettings:
    return MediaWorkerSettings(
        _env_file=None,
        database_url=SecretStr("postgresql+asyncpg://test:synthetic@127.0.0.1:1/media_test"),
        media=MediaConfiguration(
            endpoint_origin="https://storage.example.test",
            bucket="synthetic-bucket",
            region="us-east-1",
            access_key_id=SecretStr("synthetic-identifier"),
            secret_access_key=SecretStr(uuid4().hex),
        ),
        observability=None,
    )


async def test_stopped_media_worker_composes_and_closes_without_network_or_auth_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def deny_database(*_args: object, **_kwargs: object) -> NoReturn:
        raise AssertionError("Stopped worker attempted database access")

    async def deny_storage(*_args: object, **_kwargs: object) -> NoReturn:
        raise AssertionError("Stopped worker attempted S3 API access")

    monkeypatch.setattr(AsyncEngine, "connect", deny_database)
    monkeypatch.setattr(AioBaseClient, "_make_api_call", deny_storage)
    current = configuration()
    assert set(type(current).model_fields) == {"database_url", "media", "observability"}
    stop = asyncio.Event()
    stop.set()
    await run_media_worker(current, stop)


async def test_media_cli_handles_stop_and_removes_signal_handlers(
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

    def settings() -> MediaWorkerSettings:
        return current

    async def run_worker(value: MediaWorkerSettings, stop: asyncio.Event) -> None:
        assert value is current
        assert stop.is_set()

    monkeypatch.setattr(loop, "add_signal_handler", add)
    monkeypatch.setattr(loop, "remove_signal_handler", remove)
    monkeypatch.setattr(entrypoint, "MediaWorkerSettings", settings)
    monkeypatch.setattr(entrypoint, "run_media_worker", run_worker)
    await entrypoint.run()
    assert registered == removed


def test_media_cli_owns_event_loop_and_safe_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[str] = []

    async def run() -> None:
        called.append("run")

    monkeypatch.setattr(entrypoint, "run", run)
    monkeypatch.setattr(entrypoint, "configure_logging", lambda: called.append("logging"))
    entrypoint.main()
    assert called == ["logging", "run"]


def test_media_worker_rejects_nonasync_database() -> None:
    current = configuration()
    with pytest.raises(ValidationError, match="asyncpg"):
        MediaWorkerSettings(
            _env_file=None, database_url=SecretStr("sqlite:///invalid.db"), media=current.media
        )
