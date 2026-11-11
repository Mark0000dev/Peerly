import os
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema

from tests.integration.http_identity import browser as browser
from tests.integration.migrations import migrate


@pytest.fixture
async def database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if url is None:
        pytest.fail("Set TEST_DATABASE_URL to a disposable PostgreSQL database ending in _test")
    parsed = make_url(url)
    if parsed.drivername != "postgresql+asyncpg" or not (parsed.database or "").endswith("_test"):
        pytest.fail("Integration tests require postgresql+asyncpg and a database ending in _test")
    return url


@pytest.fixture
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    schema = f"test_{uuid4().hex}"
    admin = create_async_engine(database_url)
    async with admin.begin() as connection:
        await connection.execute(CreateSchema(schema))
    isolated = create_async_engine(
        database_url,
        connect_args={"server_settings": {"search_path": schema}},
    )
    try:
        yield isolated
    finally:
        await isolated.dispose()
        async with admin.begin() as connection:
            await connection.execute(DropSchema(schema, cascade=True))
        await admin.dispose()


@pytest.fixture
async def identity_engine(engine: AsyncEngine) -> AsyncEngine:
    async with engine.begin() as connection:
        await connection.run_sync(migrate, "head")
    return engine
