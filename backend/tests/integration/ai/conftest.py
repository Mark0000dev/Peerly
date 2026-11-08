import pytest
from sqlalchemy.ext.asyncio import AsyncEngine


@pytest.fixture
async def ai_engine(identity_engine: AsyncEngine) -> AsyncEngine:
    """Owner migration0017 is the sole schema authority, in the unique test schema."""
    return identity_engine
