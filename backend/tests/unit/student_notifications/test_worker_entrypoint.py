"""Configuration/CLI contracts only; no database, activation, provider or worker loop."""

import os

import pytest
from pydantic import SecretStr, ValidationError

from studymate.infrastructure.student_notifications.providers import selection_from_keys
from studymate.infrastructure.student_notifications.settings import (
    StudentNotificationDeliverySettings,
    StudentNotificationProviderSettings,
    StudentNotificationWorkerSettings,
)
from studymate.student_notifications_worker import Operation, parse_operation

ARGUMENT_ERROR_EXIT = 2


@pytest.fixture(autouse=True)
def clear_provider_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in tuple(os.environ):
        if name.startswith("STUDENT_NOTIFICATIONS_"):
            monkeypatch.delenv(name)


@pytest.mark.parametrize("arguments", [[], ["activate"], ["run", "--confirm-no-backfill"]])
def test_no_implicit_command_or_unconfirmed_activation(arguments: list[str]) -> None:
    with pytest.raises(SystemExit) as error:
        parse_operation(arguments)
    assert error.value.code == ARGUMENT_ERROR_EXIT


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [(["run"], Operation.RUN), (["activate", "--confirm-no-backfill"], Operation.ACTIVATE)],
)
def test_explicit_run_and_activation_are_distinct(
    arguments: list[str], expected: Operation
) -> None:
    assert parse_operation(arguments) == expected


def test_unconfigured_api_is_truthfully_unavailable_and_activation_needs_only_database() -> None:
    selected = selection_from_keys(StudentNotificationProviderSettings().key_material())
    assert selected.web is None
    assert selected.apns is None
    assert selected.fcm is None
    config = StudentNotificationWorkerSettings(
        database_url=SecretStr("postgresql+asyncpg://synthetic@127.0.0.1/unused_test")
    )
    assert config.database_url.get_secret_value().endswith("/unused_test")


def test_partial_provider_configuration_fails_before_network_or_worker_start() -> None:
    config = StudentNotificationProviderSettings(
        contact=SecretStr("mailto:synthetic@example.invalid")
    )
    with pytest.raises(ValueError, match="Partial Web Push"):
        selection_from_keys(config.key_material())


def test_worker_requires_matching_explicit_envelope_and_asyncpg() -> None:
    with pytest.raises(ValidationError):
        StudentNotificationDeliverySettings(
            database_url=SecretStr("postgresql+asyncpg://synthetic@127.0.0.1/unused_test"),
            envelope_key=SecretStr("invalid"),
        )
    with pytest.raises(ValidationError):
        StudentNotificationWorkerSettings(database_url=SecretStr("sqlite:///invalid"))
