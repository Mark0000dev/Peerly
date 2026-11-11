from contextlib import AsyncExitStack

import pytest
from sqlalchemy import text
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.pool import AsyncAdaptedQueuePool

from studymate.bootstrap import create_ai_admission_engine, create_change_read_engine
from tests.integration.http_identity import BrowserHarness

pytestmark = pytest.mark.integration
NAMED_POOL_CONNECTIONS = 2


@pytest.mark.parametrize("kind", ["ai", "changes"])
async def test_actual_named_factory_keeps_its_pool_and_schema_inside_browser_fixture(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
    database_url: str,
    kind: str,
) -> None:
    async with identity_engine.connect() as connection:
        schema = await connection.scalar(text("SELECT current_schema()"))
    assert isinstance(schema, str)
    factory = create_ai_admission_engine if kind == "ai" else create_change_read_engine
    engine = factory(database_url, server_settings={"search_path": schema})
    try:
        assert engine not in (identity_engine, browser.ai_engine, browser.change_engine)
        assert isinstance(engine.pool, AsyncAdaptedQueuePool)
        assert engine.pool.size() == NAMED_POOL_CONNECTIONS
        async with AsyncExitStack() as resources:
            for _ in range(NAMED_POOL_CONNECTIONS):
                connection = await resources.enter_async_context(engine.connect())
                assert await connection.scalar(text("SELECT current_schema()")) == schema
            with pytest.raises(PoolTimeoutError, match="QueuePool limit"):
                async with engine.connect():
                    pytest.fail("The actual named factory unexpectedly allowed overflow")
            async with identity_engine.connect() as core:
                assert await core.scalar(text("SELECT 1")) == 1
        assert engine.pool.checkedout() == 0
    finally:
        await engine.dispose()
