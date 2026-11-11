import asyncio
from collections.abc import AsyncIterator
from contextlib import suppress
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.infrastructure.ai.runtime.health import SqlRuntimeHealth
from tests.integration.ai.test_queue import VERSIONS


@pytest.fixture
async def ai_engine(identity_engine: AsyncEngine) -> AsyncIterator[AsyncEngine]:
    """Migrated unique schema + explicit controlled fake-worker readiness, no provider."""
    health = SqlRuntimeHealth(
        async_sessionmaker(identity_engine, expire_on_commit=False), uuid4(), VERSIONS
    )
    await health.register()
    await health.heartbeat(ready=True)
    stopping = asyncio.Event()

    async def renew() -> None:
        while not stopping.is_set():
            try:
                await asyncio.wait_for(stopping.wait(), 5)
            except TimeoutError:
                # A test may intentionally revoke/expire runtime facts. Never revive it.
                from studymate.infrastructure.ai.runtime.health import RuntimeOwnershipError

                with suppress(RuntimeOwnershipError):
                    await health.heartbeat()

    task = asyncio.create_task(renew())
    try:
        yield identity_engine
    finally:
        stopping.set()
        await task
