import pytest

from tests.load.conftest import local_database_url


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "[::1]"])
def test_owned_loopback_database_is_not_rewritten(host: str) -> None:
    value = f"postgresql+asyncpg://synthetic:private@{host}/owned_test"
    assert local_database_url(value) == value


@pytest.mark.parametrize(
    "suffix",
    [
        "remote.example.test/owned_test",
        "127.0.0.1/owned_test?host=remote.example.test",
        "localhost/owned_test?ssl=require",
    ],
)
def test_remote_or_query_override_is_rejected_before_engine_creation(suffix: str) -> None:
    value = "postgresql+asyncpg://synthetic:private@" + suffix
    with pytest.raises(ValueError, match="direct loopback") as rejected:
        local_database_url(value)
    assert "private" not in str(rejected.value)
    assert "remote.example.test" not in str(rejected.value)
