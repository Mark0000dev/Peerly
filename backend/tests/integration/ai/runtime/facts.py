"""Explicit synthetic worker facts for integration scenarios, never global readiness."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.domain.ai.jobs import Versions
from studymate.infrastructure.ai.runtime.availability import RUNTIME_HEARTBEAT_SECONDS
from studymate.infrastructure.ai.runtime.health import RuntimeOwnershipError, SqlRuntimeHealth


@asynccontextmanager
async def fake_runtime_ready(
    engine: AsyncEngine, versions: Versions
) -> AsyncIterator[SqlRuntimeHealth]:
    """Bounded actual DB readiness with no provider or physical-stop assertion.

    Call only inside a migrated disposable test schema. Cleanup cannot release an
    occupied executor token: revoke(clean=True) retains blocked ownership then.
    Explicit revocation/freshness tests are never silently revived by renewal.
    """
    health = SqlRuntimeHealth(async_sessionmaker(engine, expire_on_commit=False), uuid4(), versions)
    await health.register()
    stopping = asyncio.Event()
    renewal: asyncio.Task[None] | None = None

    async def renew() -> None:
        while not stopping.is_set():
            try:
                await asyncio.wait_for(stopping.wait(), RUNTIME_HEARTBEAT_SECONDS)
            except TimeoutError:
                with suppress(RuntimeOwnershipError):
                    await health.heartbeat()

    try:
        await health.heartbeat(ready=True)
        renewal = asyncio.create_task(renew())
        yield health
    finally:
        stopping.set()
        try:
            if renewal is not None:
                await renewal
        finally:
            await health.revoke(clean=True)
