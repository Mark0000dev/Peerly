import asyncio
from dataclasses import replace
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.identity.google import (
    GoogleAuthorization,
    GoogleCode,
    GoogleRejectedError,
)
from studymate.application.identity.login import (
    BeginGoogleLogin,
    CallbackRateLimitedError,
    CompleteGoogleLogin,
    GoogleCallbackCommand,
    HandleGoogleCallback,
)
from studymate.domain.membership import GOOGLE_ISSUER, GoogleIdentity
from studymate.infrastructure.persistence.callback_models import CallbackAttemptRecord
from studymate.infrastructure.persistence.google_login import SqlLoginUnitOfWork
from studymate.infrastructure.persistence.identity_models import SessionRecord
from studymate.infrastructure.security.login_vault import AeadLoginVault
from tests.integration.http_identity import GoogleBoundary

pytestmark = pytest.mark.integration
SOURCE = bytes(32)
INVALID = GoogleCallbackCommand(SOURCE, "invalid", None, None, malformed=True)


def state_from(url: str) -> str:
    return parse_qs(urlsplit(url).query)["state"][0]


def callback(
    engine: AsyncEngine, limit: int = 1, provider: GoogleBoundary | None = None
) -> HandleGoogleCallback:
    uow = SqlLoginUnitOfWork(async_sessionmaker(engine))
    return HandleGoogleCallback(
        uow,
        CompleteGoogleLogin(uow, provider or GoogleBoundary(), AeadLoginVault(bytes(range(32)))),
        limit,
    )


async def test_concurrent_invalid_callbacks_cannot_overspend_failure_budget(
    identity_engine: AsyncEngine,
) -> None:
    handler = callback(identity_engine)

    async def submit() -> str:
        try:
            await handler(INVALID)
        except CallbackRateLimitedError:
            return "limited"
        except GoogleRejectedError:
            return "invalid"
        raise AssertionError("Invalid callback succeeded")

    outcomes = await asyncio.gather(*(submit() for _ in range(4)))
    assert outcomes.count("invalid") == 1
    assert outcomes.count("limited") == len(outcomes) - 1
    async with async_sessionmaker(identity_engine)() as session:
        assert (
            await session.scalars(select(func.count()).select_from(CallbackAttemptRecord))
        ).one() == 1
        assert (await session.scalars(select(func.count()).select_from(SessionRecord))).one() == 0


async def test_failure_budget_is_source_bound_and_expires_without_purging_history(
    identity_engine: AsyncEngine,
) -> None:
    handler = callback(identity_engine)
    with pytest.raises(GoogleRejectedError):
        await handler(INVALID)
    with pytest.raises(GoogleRejectedError):
        await handler(replace(INVALID, source_digest=bytes(range(32))))
    with pytest.raises(CallbackRateLimitedError) as blocked:
        await handler(INVALID)
    async with async_sessionmaker(identity_engine).begin() as session:
        first = (
            await session.scalars(
                select(CallbackAttemptRecord).where(CallbackAttemptRecord.source_digest == SOURCE)
            )
        ).one()
        assert blocked.value.retry_at == first.started_at + timedelta(hours=1)
        await session.execute(
            update(CallbackAttemptRecord).values(
                started_at=func.clock_timestamp() - timedelta(hours=2)
            )
        )
    with pytest.raises(GoogleRejectedError):
        await handler(INVALID)
    async with async_sessionmaker(identity_engine)() as session:
        attempts = (await session.scalars(select(CallbackAttemptRecord))).all()
        assert len(attempts) == len({attempt.id for attempt in attempts})
        assert len(attempts) > 1


async def test_success_releases_failure_slot_with_session_commit(
    identity_engine: AsyncEngine,
) -> None:
    handler = callback(identity_engine)
    begin = BeginGoogleLogin(
        handler.unit_of_work, handler.complete.provider, handler.complete.vault
    )
    for _ in range(2):
        flow = await begin(return_to="/", source_digest=SOURCE)
        await handler(
            GoogleCallbackCommand(SOURCE, state_from(flow.redirect_url), flow.browser, "code")
        )
    async with async_sessionmaker(identity_engine)() as session:
        attempts = (await session.scalars(select(CallbackAttemptRecord))).all()
        assert len(attempts) > 1
        assert all(attempt.succeeded_at is not None for attempt in attempts)
        assert all(attempt.account_id is not None for attempt in attempts)
        assert len({attempt.account_id for attempt in attempts}) == 1
        assert (
            await session.scalars(select(func.count()).select_from(SessionRecord))
        ).one() == len(attempts)


class WaitingProvider(GoogleBoundary):
    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def exchange(
        self, code: GoogleCode, authorization: GoogleAuthorization
    ) -> GoogleIdentity:
        assert code.value
        assert authorization.nonce
        self.started.set()
        await self.release.wait()
        return GoogleIdentity(GOOGLE_ISSUER, "controlled-subject")


async def test_inflight_and_cancelled_provider_attempt_remain_bounded(
    identity_engine: AsyncEngine,
) -> None:
    provider = WaitingProvider()
    handler = callback(identity_engine, provider=provider)
    flow = await BeginGoogleLogin(handler.unit_of_work, provider, handler.complete.vault)(
        return_to="/", source_digest=SOURCE
    )
    pending = asyncio.create_task(
        handler(GoogleCallbackCommand(SOURCE, state_from(flow.redirect_url), flow.browser, "code"))
    )
    try:
        await asyncio.wait_for(provider.started.wait(), timeout=2)
        with pytest.raises(CallbackRateLimitedError):
            await asyncio.wait_for(handler(INVALID), timeout=2)
    finally:
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
    with pytest.raises(CallbackRateLimitedError):
        await handler(INVALID)
