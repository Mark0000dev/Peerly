import pytest
from pydantic import SecretStr, ValidationError

from studymate.config import AiHttpConfiguration, AuthenticationConfiguration, Settings


@pytest.mark.parametrize("url", ["sqlite+aiosqlite:///test.db", "postgresql://localhost/test"])
def test_sync_or_non_postgresql_drivers_are_rejected(url: str) -> None:
    with pytest.raises(ValidationError, match="must use postgresql\\+asyncpg"):
        Settings(database_url=SecretStr(url))


def test_database_password_is_not_in_settings_representation() -> None:
    settings = Settings(database_url=SecretStr("postgresql+asyncpg://user:secret@localhost/test"))
    assert "secret" not in repr(settings)


@pytest.mark.parametrize("key", ["", "ff" * 31, "z" * 64])
def test_authentication_rejects_invalid_secret_keys(key: str) -> None:

    with pytest.raises(ValidationError, match="32-byte"):
        AuthenticationConfiguration(
            client_id="client",
            client_secret=SecretStr("synthetic"),
            public_origin="https://app.test",
            envelope_key=SecretStr(key),
            browser_signing_key=SecretStr("02" * 32),
            code_key=SecretStr("03" * 32),
        )


@pytest.mark.parametrize(
    "origin",
    ["http://app.test", "https://app.test/", "https://user:pass@app.test", "https://app.test?x=1"],
)
def test_authentication_rejects_unsafe_public_origins(origin: str) -> None:

    with pytest.raises(ValidationError, match="HTTPS origin"):
        AuthenticationConfiguration(
            client_id="client",
            client_secret=SecretStr("synthetic"),
            public_origin=origin,
            envelope_key=SecretStr("01" * 32),
            browser_signing_key=SecretStr("02" * 32),
            code_key=SecretStr("03" * 32),
        )


def test_authentication_rejects_shared_keys_and_empty_google_secret() -> None:

    with pytest.raises(ValidationError, match="distinct"):
        AuthenticationConfiguration(
            client_id="client",
            client_secret=SecretStr("synthetic"),
            public_origin="https://app.test",
            envelope_key=SecretStr("01" * 32),
            browser_signing_key=SecretStr("01" * 32),
            code_key=SecretStr("03" * 32),
        )
    with pytest.raises(ValidationError, match="Google client secret"):
        AuthenticationConfiguration(
            client_id="client",
            client_secret=SecretStr(""),
            public_origin="https://app.test",
            envelope_key=SecretStr("01" * 32),
            browser_signing_key=SecretStr("02" * 32),
            code_key=SecretStr("03" * 32),
        )


@pytest.mark.parametrize(
    "field",
    [
        "callback_failures_per_hour",
        "google_starts_per_hour",
        "email_deliveries_per_account_hour",
        "email_deliveries_per_address_hour",
        "email_starts_per_source_hour",
    ],
)
def test_authentication_rate_limits_cannot_be_disabled_by_zero_configuration(field: str) -> None:
    configuration = AuthenticationConfiguration(
        client_id="client",
        client_secret=SecretStr("synthetic"),
        public_origin="https://app.test",
        envelope_key=SecretStr("01" * 32),
        browser_signing_key=SecretStr("02" * 32),
        code_key=SecretStr("03" * 32),
    )
    with pytest.raises(ValidationError):
        AuthenticationConfiguration.model_validate({**configuration.model_dump(), field: 0})


@pytest.mark.parametrize("budget", [0, -1, 2.01, float("nan"), float("inf")])
def test_ai_http_budget_cannot_exceed_admission_deadline(budget: float) -> None:
    with pytest.raises(ValidationError):
        AiHttpConfiguration(request_budget_seconds=budget)


def test_ai_configuration_has_no_executor_enable_switch() -> None:
    with pytest.raises(ValidationError):
        AiHttpConfiguration.model_validate({"accepting": True})
