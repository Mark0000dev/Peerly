"""Owner-operated assignment definitions against actual migrated, isolated PostgreSQL."""

import asyncio
from dataclasses import dataclass, replace
from datetime import datetime
from itertools import pairwise
from uuid import UUID, uuid4

import pytest
from deployment.backend.operator_access import Assignment, OperatorAssignmentError, execute
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from studymate.domain.membership import GOOGLE_ISSUER
from studymate.infrastructure.operator.models import (
    OperatorAccessRecord,
    OperatorAccessRevisionRecord,
)
from studymate.infrastructure.persistence.identity_claims import retire_deleted_claims
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    ExternalIdentityRecord,
)
from tests.integration.student_actor import Actor, actor

pytestmark = pytest.mark.integration
INITIAL_VERSION = 1
REVOKED_VERSION = 2
REGRANTED_VERSION = 3


@dataclass(frozen=True, slots=True)
class AccessCli:
    sessions: async_sessionmaker[AsyncSession]
    performer: Actor
    target: Actor
    command: Assignment


async def google_actor(engine: AsyncEngine) -> Actor:
    owner = await actor(engine, verified=False)
    async with async_sessionmaker(engine).begin() as session:
        at = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(at, datetime)
        session.add(
            ExternalIdentityRecord(
                id=uuid4(),
                account_id=owner.id,
                issuer=GOOGLE_ISSUER,
                subject=f"synthetic-cli-{owner.id}",
                created_at=at,
            )
        )
    return owner


async def prepared(engine: AsyncEngine, *, google_target: bool = True) -> AccessCli:
    performer = await google_actor(engine)
    target = await google_actor(engine) if google_target else await actor(engine, verified=False)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        database = await session.scalar(select(func.current_database()))
        assert isinstance(database, str)
    return AccessCli(
        sessions, performer, target, Assignment(database, performer.id, target.id, 0, True)
    )


async def revisions(api: AccessCli) -> tuple[tuple[int, bool, UUID | None], ...]:
    async with api.sessions() as session:
        rows = (
            await session.execute(
                select(
                    OperatorAccessRevisionRecord.version,
                    OperatorAccessRevisionRecord.active,
                    OperatorAccessRevisionRecord.changed_by_id,
                )
                .where(OperatorAccessRevisionRecord.account_id == api.target.id)
                .order_by(OperatorAccessRevisionRecord.version)
            )
        ).all()
        return tuple((row[0], row[1], row[2]) for row in rows)


async def apply(
    api: AccessCli, command: Assignment, *, apply_change: bool = True
) -> dict[str, object]:
    async with api.sessions.begin() as session:
        return await execute(session, command, apply=apply_change)


async def test_plan_never_creates_or_advances_a_grant(identity_engine: AsyncEngine) -> None:
    api = await prepared(identity_engine)
    async with api.sessions.begin() as session:
        plan = await execute(session, api.command, apply=False)
    assert plan["status"] == "planned"
    assert plan["resulting_version"] == INITIAL_VERSION
    assert await revisions(api) == ()
    async with api.sessions() as session:
        assert await session.get(OperatorAccessRecord, api.target.id) is None
    await apply(api, api.command)
    before = await revisions(api)
    async with api.sessions.begin() as session:
        next_plan = await execute(
            session,
            replace(api.command, expected_version=INITIAL_VERSION, active=False),
            apply=False,
        )
    assert next_plan["resulting_version"] == REVOKED_VERSION
    assert await revisions(api) == before
    async with api.sessions() as session:
        current = await session.get(OperatorAccessRecord, api.target.id)
        assert current is not None
        assert current.current_version == INITIAL_VERSION


async def test_grant_revoke_regrant_retains_each_original_performer(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    second_performer = await google_actor(identity_engine)
    first = await apply(api, api.command)
    revoked = await apply(
        api,
        replace(
            api.command,
            performed_by=second_performer.id,
            expected_version=INITIAL_VERSION,
            active=False,
        ),
    )
    regranted = await apply(api, replace(api.command, expected_version=REVOKED_VERSION))
    assert first["resulting_version"] == INITIAL_VERSION
    assert revoked["resulting_version"] == REVOKED_VERSION
    assert regranted["resulting_version"] == REGRANTED_VERSION
    assert await revisions(api) == (
        (INITIAL_VERSION, True, api.performer.id),
        (REVOKED_VERSION, False, second_performer.id),
        (REGRANTED_VERSION, True, api.performer.id),
    )
    async with api.sessions() as session:
        root = await session.get(OperatorAccessRecord, api.target.id)
        assert root is not None
        assert root.current_version == REGRANTED_VERSION
        rows = tuple(
            await session.scalars(
                select(OperatorAccessRevisionRecord)
                .where(OperatorAccessRevisionRecord.account_id == api.target.id)
                .order_by(OperatorAccessRevisionRecord.version)
            )
        )
        assert all(
            previous.changed_at <= following.changed_at for previous, following in pairwise(rows)
        )


@pytest.mark.parametrize("apply_change", [False, True])
async def test_stale_expected_version_rejects_without_history_mutation(
    identity_engine: AsyncEngine, apply_change: bool
) -> None:
    api = await prepared(identity_engine)
    await apply(api, api.command)
    before = await revisions(api)
    with pytest.raises(OperatorAssignmentError, match=r"^stale_version$"):
        await apply(api, replace(api.command, active=False), apply_change=apply_change)
    assert await revisions(api) == before


@pytest.mark.parametrize("already_granted", [False, True])
async def test_caller_rollback_keeps_root_and_all_revision_history(
    identity_engine: AsyncEngine, already_granted: bool
) -> None:
    api = await prepared(identity_engine)
    if already_granted:
        await apply(api, api.command)
    command = (
        replace(api.command, expected_version=INITIAL_VERSION, active=False)
        if already_granted
        else api.command
    )
    before = await revisions(api)

    async def aborted_write() -> None:
        async with api.sessions.begin() as session:
            await execute(session, command, apply=True)
            raise RuntimeError("synthetic rollback")

    with pytest.raises(RuntimeError, match=r"^synthetic rollback$"):
        await aborted_write()
    assert await revisions(api) == before
    async with api.sessions() as session:
        root = await session.get(OperatorAccessRecord, api.target.id)
        if already_granted:
            assert root is not None
            assert root.current_version == INITIAL_VERSION
        else:
            assert root is None


@pytest.mark.parametrize("state", ["deleted", "banned", "retired_google"])
async def test_unavailable_target_cannot_regrant_but_existing_grant_can_be_revoked(
    identity_engine: AsyncEngine, state: str
) -> None:
    api = await prepared(identity_engine)
    await apply(api, api.command)
    async with api.sessions.begin() as session:
        at = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(at, datetime)
        if state == "banned":
            await session.execute(
                update(AccountRecord).where(AccountRecord.id == api.target.id).values(banned_at=at)
            )
        else:
            await session.execute(
                update(AccountRecord).where(AccountRecord.id == api.target.id).values(deleted_at=at)
            )
            if state == "retired_google":
                await retire_deleted_claims(session, api.target.id)
    revoked = await apply(api, replace(api.command, expected_version=INITIAL_VERSION, active=False))
    assert revoked["resulting_version"] == REVOKED_VERSION
    with pytest.raises(OperatorAssignmentError, match=r"^account_unavailable$"):
        await apply(api, replace(api.command, expected_version=REVOKED_VERSION))
    assert await revisions(api) == (
        (INITIAL_VERSION, True, api.performer.id),
        (REVOKED_VERSION, False, api.performer.id),
    )
    if state == "retired_google":
        async with api.sessions() as session:
            identity = (
                await session.scalars(
                    select(ExternalIdentityRecord).where(
                        ExternalIdentityRecord.account_id == api.target.id
                    )
                )
            ).one()
            assert identity.retired_at is not None


async def test_never_linked_google_target_is_not_given_an_assignment(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine, google_target=False)
    with pytest.raises(OperatorAssignmentError, match=r"^google_identity_unavailable$"):
        await apply(api, api.command)
    assert await revisions(api) == ()
    async with api.sessions() as session:
        assert await session.get(OperatorAccessRecord, api.target.id) is None
    with pytest.raises(OperatorAssignmentError, match=r"^no_assignment_to_revoke$"):
        await apply(api, replace(api.command, active=False))


async def test_same_expected_version_concurrent_commands_have_one_committed_winner(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    second_performer = await google_actor(identity_engine)
    ready = (asyncio.Event(), asyncio.Event())
    start = asyncio.Event()

    async def contend(index: int, performer: UUID) -> str:
        try:
            async with api.sessions.begin() as session:
                await session.connection()
                ready[index].set()
                await start.wait()
                await execute(session, replace(api.command, performed_by=performer), apply=True)
        except OperatorAssignmentError as error:
            return str(error)
        return "applied"

    async with asyncio.timeout(10), asyncio.TaskGroup() as group:
        tasks = (
            group.create_task(contend(0, api.performer.id)),
            group.create_task(contend(1, second_performer.id)),
        )
        await asyncio.gather(*(event.wait() for event in ready))
        start.set()
        outcomes = await asyncio.gather(*tasks)
    assert sorted(outcomes) == ["applied", "stale_version"]
    rows = await revisions(api)
    assert len(rows) == 1
    version, active, changed_by = rows[0]
    assert version == INITIAL_VERSION
    assert active
    assert changed_by in (api.performer.id, second_performer.id)
    async with api.sessions() as session:
        root = await session.get(OperatorAccessRecord, api.target.id)
        assert root is not None
        assert root.current_version == INITIAL_VERSION


async def test_wrong_database_execute_guard_never_creates_history(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    with pytest.raises(OperatorAssignmentError, match=r"^wrong_database$"):
        await apply(api, replace(api.command, database=f"{api.command.database}_mismatch"))
    assert await revisions(api) == ()
    async with api.sessions() as session:
        assert await session.get(OperatorAccessRecord, api.target.id) is None


@pytest.mark.parametrize("state", ["missing", "deleted", "banned", "no_google"])
async def test_missing_or_unavailable_performer_cannot_create_assignment_history(
    identity_engine: AsyncEngine,
    state: str,
) -> None:
    api = await prepared(identity_engine)
    performer_id = api.performer.id
    if state == "missing":
        performer_id = uuid4()
        code = "account_missing"
    elif state == "no_google":
        performer_id = (await actor(identity_engine, verified=False)).id
        code = "google_identity_unavailable"
    else:
        async with api.sessions.begin() as session:
            at = await session.scalar(select(func.clock_timestamp()))
            assert isinstance(at, datetime)
            statement = update(AccountRecord).where(AccountRecord.id == performer_id)
            if state == "deleted":
                await session.execute(statement.values(deleted_at=at))
            else:
                await session.execute(statement.values(banned_at=at))
        code = "account_unavailable"
    with pytest.raises(OperatorAssignmentError, match=f"^{code}$"):
        await apply(api, replace(api.command, performed_by=performer_id))
    assert await revisions(api) == ()
    async with api.sessions() as session:
        assert await session.get(OperatorAccessRecord, api.target.id) is None
