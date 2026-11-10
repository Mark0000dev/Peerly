"""Trusted Google callbacks cannot multiply actors, revive sessions or evade bans."""

import asyncio
from uuid import UUID

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.identity.google import GoogleCode
from studymate.application.identity.login import (
    AccountUnavailableError,
    BeginGoogleLogin,
    CompleteGoogleLogin,
    LoginStarted,
)
from studymate.application.identity.sessions import ReadIdentity, SessionCredential
from studymate.infrastructure.persistence.google_login import (
    SqlLoginTransaction,
    SqlLoginUnitOfWork,
)
from studymate.infrastructure.persistence.identity_claims import retire_deleted_claims
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    ExternalIdentityRecord,
)
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityUnitOfWork
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.integration.test_google_login import SOURCE, GoogleProviderDouble, state_from, vault

pytestmark = pytest.mark.integration


def services(engine: AsyncEngine) -> tuple[BeginGoogleLogin, CompleteGoogleLogin, ReadIdentity]:
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    uow = SqlLoginUnitOfWork(sessions)
    provider = GoogleProviderDouble()
    return (
        BeginGoogleLogin(uow, provider, vault()),
        CompleteGoogleLogin(uow, provider, vault()),
        ReadIdentity(SqlIdentityUnitOfWork(sessions), Sha256SessionHasher()),
    )


async def finish(complete: CompleteGoogleLogin, flow: LoginStarted) -> SessionCredential:
    return (
        await complete(
            state=state_from(flow.redirect_url), browser=flow.browser, code=GoogleCode("code")
        )
    ).credential


async def test_concurrent_fresh_google_callbacks_share_one_new_actor_after_deletion(
    identity_engine: AsyncEngine,
) -> None:
    begin, complete, read = services(identity_engine)
    original = await finish(complete, await begin(return_to="/", source_digest=SOURCE))
    old_id = (await read(original)).session.account_id
    sessions = async_sessionmaker(identity_engine)
    async with sessions.begin() as session:
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == old_id)
            .values(deleted_at=func.clock_timestamp())
        )
        await retire_deleted_claims(session, old_id)
    first, second = await asyncio.gather(
        begin(return_to="/", source_digest=SOURCE), begin(return_to="/", source_digest=SOURCE)
    )
    credentials = await asyncio.gather(finish(complete, first), finish(complete, second))
    identities = await asyncio.gather(*(read(value) for value in credentials))
    new_ids = {value.session.account_id for value in identities}
    assert len(new_ids) == 1
    assert old_id not in new_ids
    assert all(value.membership is None and value.registration is None for value in identities)
    async with sessions() as session:
        links = tuple(await session.scalars(select(ExternalIdentityRecord)))
        assert {value.account_id for value in links} == new_ids | {old_id}
        assert sum(value.retired_at is None for value in links) == 1


async def test_ban_of_retained_incarnation_restricts_the_new_account_without_restoring_history(
    identity_engine: AsyncEngine,
) -> None:
    begin, complete, read = services(identity_engine)
    original = await finish(complete, await begin(return_to="/", source_digest=SOURCE))
    old_id = (await read(original)).session.account_id
    sessions = async_sessionmaker(identity_engine)
    async with sessions.begin() as session:
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == old_id)
            .values(deleted_at=func.clock_timestamp())
        )
        await retire_deleted_claims(session, old_id)
    fresh = await finish(complete, await begin(return_to="/", source_digest=SOURCE))
    new_id = (await read(fresh)).session.account_id
    assert new_id != old_id
    async with sessions.begin() as session:
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == old_id)
            .values(banned_at=func.clock_timestamp())
        )
    restricted = await read(fresh)
    assert restricted.banned
    assert restricted.membership is None
    assert restricted.session.account_id == new_id
    async with sessions.begin() as session:
        await session.execute(
            update(AccountRecord).where(AccountRecord.id == old_id).values(banned_at=None)
        )
    assert not (await read(fresh)).banned


@pytest.mark.parametrize("change", ["delete", "ban_deleted"])
async def test_callback_rechecks_lifecycle_after_prelock_identity_lookup(
    identity_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    begin, complete, read = services(identity_engine)
    credential = await finish(complete, await begin(return_to="/", source_digest=SOURCE))
    old_id = (await read(credential)).session.account_id
    flow = await begin(return_to="/", source_digest=SOURCE)
    entered, release = asyncio.Event(), asyncio.Event()
    original = SqlLoginTransaction._lock_google_scope

    async def paused(
        transaction: SqlLoginTransaction,
        identities: tuple[ExternalIdentityRecord, ...],
        previous: bytes | None,
    ) -> dict[UUID, AccountRecord]:
        entered.set()
        await release.wait()
        return await original(transaction, identities, previous)

    monkeypatch.setattr(SqlLoginTransaction, "_lock_google_scope", paused)
    task = asyncio.create_task(finish(complete, flow))
    try:
        await asyncio.wait_for(entered.wait(), timeout=2)
        async with async_sessionmaker(identity_engine).begin() as session:
            await session.execute(
                update(AccountRecord)
                .where(AccountRecord.id == old_id)
                .values(deleted_at=func.clock_timestamp())
            )
            await retire_deleted_claims(session, old_id)
            if change == "ban_deleted":
                await session.execute(
                    update(AccountRecord)
                    .where(AccountRecord.id == old_id)
                    .values(banned_at=func.clock_timestamp())
                )
        release.set()
        if change == "ban_deleted":
            with pytest.raises(AccountUnavailableError):
                await task
        else:
            fresh = await task
            assert (await read(fresh)).session.account_id != old_id
    finally:
        release.set()
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
