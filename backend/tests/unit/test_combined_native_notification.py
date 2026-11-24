"""Native completion preserves the existing atomic notification logout adapter."""

from typing import NoReturn

import httpx2
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.bootstrap import _authentication_services, _mount_native_identity
from studymate.config import AuthenticationConfiguration
from studymate.infrastructure.persistence.native_login import NativeAttemptRecord
from studymate.infrastructure.persistence.native_login_models import (
    NativeAttemptRecord as RegisteredNativeAttemptRecord,
)
from studymate.infrastructure.persistence.schema import MODELS


def no_provider(_request: httpx2.Request) -> NoReturn:
    raise AssertionError("Composition must not perform provider I/O")


async def test_native_composition_retains_notification_logout_and_existing_auth() -> None:
    configuration = AuthenticationConfiguration(
        client_id="schema-only",
        client_secret=SecretStr("synthetic"),
        public_origin="https://schema.invalid",
        envelope_key=SecretStr("01" * 32),
        browser_signing_key=SecretStr("02" * 32),
        code_key=SecretStr("03" * 32),
    )
    sessions = async_sessionmaker[AsyncSession]()
    async with httpx2.AsyncClient(transport=httpx2.MockTransport(no_provider)) as http:
        original = _authentication_services(configuration, sessions, http)
        assert original.logout_installation is not None
        combined = _mount_native_identity(FastAPI(), original, sessions)
        assert combined.native_complete is not None
        assert combined.logout_installation is original.logout_installation
        assert combined.logout is original.logout
        assert combined.begin is original.begin
        assert combined.complete is original.complete
        assert combined.signer is original.signer
        assert combined.browser is original.browser


def test_combined_registry_contains_one_exact_native_mapping() -> None:
    assert NativeAttemptRecord is RegisteredNativeAttemptRecord
    assert sum(model is NativeAttemptRecord for model in MODELS) == 1
    assert sum(model.__tablename__ == "native_login_attempts" for model in MODELS) == 1
