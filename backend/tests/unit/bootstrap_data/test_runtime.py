"""Resource boundary configuration and safe failure/cancellation semantics."""

import asyncio

import pytest
from sqlalchemy.exc import SQLAlchemyError

from studymate.application.bootstrap_data.ports import (
    BootstrapDatabaseConfigurationError,
    BootstrapDatabaseOperationError,
)
from studymate.infrastructure.bootstrap_data import runtime


@pytest.mark.parametrize(
    "url", ["PRIVATE_INVALID", "sqlite:///forbidden", "postgresql+asyncpg://host"]
)
async def test_database_configuration_rejected_without_connecting(url: str) -> None:
    with pytest.raises(BootstrapDatabaseConfigurationError):
        async with runtime.open_bootstrap_database(url):
            pytest.fail("Invalid configuration must not yield a session factory")


class EngineBoundary:
    def __init__(self) -> None:
        self.disposed = False

    async def dispose(self) -> None:
        self.disposed = True


@pytest.mark.parametrize("cancelled", [False, True])
async def test_resource_disposes_and_preserves_cancellation_or_sanitizes_sql_errors(
    monkeypatch: pytest.MonkeyPatch, cancelled: bool
) -> None:
    # Resource-only double: this test performs no query or fake persistence.
    engine = EngineBoundary()

    def create(_url: object, **_options: object) -> EngineBoundary:
        return engine

    monkeypatch.setattr(runtime, "create_async_engine", create)
    expected = asyncio.CancelledError if cancelled else BootstrapDatabaseOperationError

    async def fail_with_resource() -> None:
        async with runtime.open_bootstrap_database("postgresql+asyncpg://localhost/synthetic_test"):
            if cancelled:
                raise asyncio.CancelledError
            raise SQLAlchemyError("PRIVATE_SQL_PAYLOAD")

    with pytest.raises(expected) as caught:
        await fail_with_resource()
    assert engine.disposed
    assert "PRIVATE" not in str(caught.value)
