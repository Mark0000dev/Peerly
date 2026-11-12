import pytest
from sqlalchemy.engine import make_url

from tests.integration.conftest import database_url as database_url
from tests.integration.conftest import engine as engine
from tests.integration.conftest import identity_engine as identity_engine
from tests.integration.http_identity import browser as browser


def local_database_url(value: str) -> str:
    parsed = make_url(value)
    if parsed.host not in {"localhost", "127.0.0.1", "::1"} or parsed.query:
        raise ValueError("Load scenarios require a direct loopback disposable PostgreSQL URL")
    return value


@pytest.fixture(name="database_url")
async def guarded_database_url(database_url: str) -> str:
    # Override the imported fixture under its actual name. Its own dependency
    # resolves the preceding integration fixture, preserving driver/_test checks.
    # Nothing requests this chain for the pure measurement tests.
    return local_database_url(database_url)
