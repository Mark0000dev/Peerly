import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from http import HTTPStatus
from uuid import UUID

import pytest
from sqlalchemy import event, func, select, update
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.domain.profiles import ProfileRevision
from studymate.infrastructure.persistence.identity_models import AccountRecord, SessionRecord
from studymate.infrastructure.persistence.profiles import SqlProfileTransaction
from studymate.infrastructure.persistence.transactions import open_transaction
from tests.integration.http_identity import BrowserHarness, verified, write_headers
from tests.integration.test_profile_http import payload

pytestmark = pytest.mark.integration


@dataclass(frozen=True, slots=True)
class HeldReader:
    entered: asyncio.Event
    release: asyncio.Event


@pytest.fixture
async def held_reader(
    identity_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[HeldReader]:
    entered, release = asyncio.Event(), asyncio.Event()
    original = SqlProfileTransaction.profile

    async def hold(
        transaction: SqlProfileTransaction,
        account_id: UUID,
        version: int | None = None,
    ) -> ProfileRevision | None:
        if not entered.is_set():
            entered.set()
            await release.wait()
        return await original(transaction, account_id, version)

    def bounded_lock(connection: Connection) -> None:
        connection.exec_driver_sql("SET LOCAL lock_timeout = '100ms'")

    event.listen(identity_engine.sync_engine, "begin", bounded_lock)
    monkeypatch.setattr(SqlProfileTransaction, "profile", hold)
    try:
        yield HeldReader(entered, release)
    finally:
        release.set()
        event.remove(identity_engine.sync_engine, "begin", bounded_lock)


async def test_parallel_profile_onboarding_goal_help_reads_share_real_identity_locks(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
    held_reader: HeldReader,
) -> None:
    await verified(browser, identity_engine)
    first = asyncio.create_task(browser.client.get("/api/v1/me/profile"))
    try:
        await asyncio.wait_for(held_reader.entered.wait(), timeout=3)
        others = await asyncio.wait_for(
            asyncio.gather(
                browser.client.get("/api/v1/me/profile"),
                browser.client.get("/api/v1/me/onboarding"),
                browser.client.get("/api/v1/me/goal"),
                browser.client.get("/api/v1/me/help-subjects"),
            ),
            timeout=3,
        )
        assert [response.status_code for response in others] == [HTTPStatus.OK] * len(others)
        assert not first.done()
    finally:
        held_reader.release.set()
        assert (await first).status_code == HTTPStatus.OK


async def test_writer_cannot_upgrade_shared_reader_or_bypass_profile_cas(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
    held_reader: HeldReader,
) -> None:
    await verified(browser, identity_engine)
    headers = await write_headers(browser.client)
    first = asyncio.create_task(browser.client.get("/api/v1/me/profile"))
    try:
        await asyncio.wait_for(held_reader.entered.wait(), timeout=3)
        blocked = await browser.client.put("/api/v1/me/profile", json=payload(), headers=headers)
        assert blocked.status_code == HTTPStatus.SERVICE_UNAVAILABLE
        assert blocked.json()["code"] == "storage_unavailable"
    finally:
        held_reader.release.set()
        assert (await first).status_code == HTTPStatus.OK
    committed = await browser.client.put("/api/v1/me/profile", json=payload(), headers=headers)
    assert committed.status_code == HTTPStatus.OK
    stale = await browser.client.put(
        "/api/v1/me/profile",
        json=payload(),
        headers=await write_headers(browser.client),
    )
    assert stale.status_code == HTTPStatus.CONFLICT


@pytest.mark.parametrize("mutation", ["ban", "delete", "revoke"])
async def test_shared_reader_keeps_ban_delete_and_session_revocation_fences(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
    held_reader: HeldReader,
    mutation: str,
) -> None:
    account_id = await verified(browser, identity_engine)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    first = asyncio.create_task(browser.client.get("/api/v1/me/profile"))
    try:
        await asyncio.wait_for(held_reader.entered.wait(), timeout=3)
        if mutation == "revoke":
            statement = (
                update(SessionRecord)
                .where(SessionRecord.account_id == account_id)
                .values(
                    revoked_at=func.clock_timestamp(),
                )
            )
        else:
            statement = (
                update(AccountRecord)
                .where(AccountRecord.id == account_id)
                .values(
                    **{"banned_at" if mutation == "ban" else "deleted_at": func.clock_timestamp()},
                )
            )
        with pytest.raises(DBAPIError) as captured:
            async with sessions.begin() as session:
                await session.execute(statement)
        assert getattr(captured.value.orig, "sqlstate", None) == "55P03"
        assert not first.done()
    finally:
        held_reader.release.set()
        assert (await first).status_code == HTTPStatus.OK
    async with sessions.begin() as session:
        await session.execute(statement)
    denied = await browser.client.get("/api/v1/me/profile")
    assert denied.status_code == (
        HTTPStatus.FORBIDDEN if mutation == "ban" else HTTPStatus.UNAUTHORIZED
    )
    async with sessions() as session:
        if mutation == "ban":
            changed = await session.scalar(
                select(AccountRecord.banned_at).where(AccountRecord.id == account_id)
            )
            assert isinstance(changed, datetime)


@pytest.mark.parametrize("mutation", ["statement", "pending_orm"])
async def test_guarded_read_unit_rejects_accidental_writes_before_commit(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
    mutation: str,
) -> None:
    account_id = await verified(browser, identity_engine)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)

    async def attempt() -> None:
        async with open_transaction(sessions, read_only=True) as session:
            if mutation == "statement":
                await session.execute(
                    update(AccountRecord)
                    .where(AccountRecord.id == account_id)
                    .values(
                        banned_at=func.clock_timestamp(),
                    )
                )
            else:
                account = await session.get(AccountRecord, account_id)
                assert account is not None
                at = await session.scalar(select(func.clock_timestamp()))
                assert isinstance(at, datetime)
                account.banned_at = at

    with pytest.raises(RuntimeError, match="Read-only identity unit cannot"):
        await attempt()
    async with sessions() as session:
        assert (
            await session.scalar(
                select(AccountRecord.banned_at).where(AccountRecord.id == account_id)
            )
            is None
        )
