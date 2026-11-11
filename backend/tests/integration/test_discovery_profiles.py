import asyncio
from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

import studymate.infrastructure.persistence.discovery_profiles as profiles_module
from studymate.application.discovery.profiles import (
    DiscoveryProfileUnavailableError,
    ReadDiscoveryProfile,
)
from studymate.application.idempotency import IntentKey
from studymate.application.safety.blocks import ChangeBlockCommand, ChangeOwnBlock
from studymate.infrastructure.observability.origin import ExecutionOrigin
from studymate.infrastructure.persistence.blocks import SqlBlockUnitOfWork
from studymate.infrastructure.persistence.discovery_profiles import SqlDiscoveryProfileUnitOfWork
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    InstitutionalBindingRecord,
)
from studymate.infrastructure.persistence.report_models import ProfileAccessRecord
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.integration.migrations import run_revision_step
from tests.integration.profile_lifecycle_fixture import command as visibility_command
from tests.integration.profile_lifecycle_fixture import services as visibility_services
from tests.integration.safety_fixture import prepared

pytestmark = pytest.mark.integration


def reader(engine: AsyncEngine) -> ReadDiscoveryProfile:
    return ReadDiscoveryProfile(
        SqlDiscoveryProfileUnitOfWork(async_sessionmaker(engine, expire_on_commit=False)),
        Sha256SessionHasher(),
    )


async def test_peer_profile_creates_exact_owned_disclosure_with_no_institutional_identity(
    identity_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    viewer, target, previous = await prepared(identity_engine)
    origin = ExecutionOrigin(uuid4(), uuid4(), "a" * 32, "b" * 16)
    monkeypatch.setattr(profiles_module, "current_origin", lambda: origin)
    result = await reader(identity_engine)(viewer.credential, target.id)
    assert result.profile.account_id == target.id
    assert result.photo.account_id == target.id
    assert result.goal is not None
    assert result.goal.goal.account_id == target.id
    assert result.access_context.viewer_id == viewer.id
    assert result.access_context.snapshot.goal_id == result.goal.goal.id
    assert "mail.apu.edu.my" not in repr(result)
    async with async_sessionmaker(identity_engine)() as session:
        row = await session.get(ProfileAccessRecord, result.access_context.id)
        assert row is not None
        assert row.viewer_id == viewer.id
        assert row.target_id == target.id
        assert row.profile_version == result.profile.version
        assert row.photo_version == result.photo.version
        assert row.request_id == origin.request_id
        assert row.action_id == origin.action_id
        assert row.trace_id == origin.trace_id
        assert row.span_id == origin.span_id
        earlier = await session.get(ProfileAccessRecord, previous.id)
        assert earlier is not None
        assert earlier.request_id is None


@pytest.mark.parametrize("state", ["unknown", "banned", "deleted", "unverified", "hidden"])
async def test_unavailable_peer_never_commits_disclosure(
    identity_engine: AsyncEngine, state: str
) -> None:
    viewer, target, _ = await prepared(identity_engine)
    sessions = async_sessionmaker(identity_engine)
    target_id = target.id
    async with sessions.begin() as session:
        if state in {"banned", "deleted"}:
            column = AccountRecord.banned_at if state == "banned" else AccountRecord.deleted_at
            await session.execute(
                update(AccountRecord)
                .where(AccountRecord.id == target.id)
                .values({column: func.clock_timestamp()})
            )
        elif state == "unverified":
            await session.execute(
                update(InstitutionalBindingRecord)
                .where(InstitutionalBindingRecord.account_id == target.id)
                .values(revoked_at=func.clock_timestamp())
            )
        elif state == "unknown":
            target_id = uuid4()
        before = await session.scalar(select(func.count()).select_from(ProfileAccessRecord))
    if state == "hidden":
        visibility, _ = visibility_services(identity_engine)
        await visibility(visibility_command(target))
    with pytest.raises(DiscoveryProfileUnavailableError):
        await reader(identity_engine)(viewer.credential, target_id)
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(ProfileAccessRecord)) == before


async def test_either_direction_block_denies_peer_profile_until_both_removed(
    identity_engine: AsyncEngine,
) -> None:
    viewer, target, context = await prepared(identity_engine)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    read = reader(identity_engine)
    reverse = await read(target.credential, viewer.id)
    change = ChangeOwnBlock(
        SqlBlockUnitOfWork(sessions),
        Sha256SessionHasher(),
        HmacIntentFingerprinter(bytes(range(32))),
    )
    first = ChangeBlockCommand(
        viewer.credential, target.id, True, 0, IntentKey(str(uuid4())), context.id
    )
    second = ChangeBlockCommand(
        target.credential, viewer.id, True, 0, IntentKey(str(uuid4())), reverse.access_context.id
    )
    await asyncio.gather(change(first), change(second))
    with pytest.raises(DiscoveryProfileUnavailableError):
        await read(viewer.credential, target.id)
    unblocked = await change(
        replace(first, blocked=False, expected_version=1, intent_key=IntentKey(str(uuid4())))
    )
    with pytest.raises(DiscoveryProfileUnavailableError):
        await read(viewer.credential, target.id)
    await change(
        replace(second, blocked=False, expected_version=1, intent_key=IntentKey(str(uuid4())))
    )
    restored = await read(viewer.credential, target.id)
    assert restored.profile.account_id == target.id
    assert restored.own_block.version == unblocked.version
    assert not restored.own_block.blocked


async def test_reciprocal_profile_reads_share_stable_account_lock_order(
    identity_engine: AsyncEngine,
) -> None:
    viewer, target, _ = await prepared(identity_engine)
    read = reader(identity_engine)
    first, second = await asyncio.wait_for(
        asyncio.gather(read(viewer.credential, target.id), read(target.credential, viewer.id)),
        timeout=5,
    )
    assert first.profile.account_id == target.id
    assert second.profile.account_id == viewer.id


async def test_disclosure_downgrade_cannot_erase_retained_execution_origin(
    identity_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:

    viewer, target, _ = await prepared(identity_engine)
    origin = ExecutionOrigin(uuid4(), None, None, None)
    monkeypatch.setattr(profiles_module, "current_origin", lambda: origin)
    result = await reader(identity_engine)(viewer.credential, target.id)
    with pytest.raises(RuntimeError, match="retained profile disclosure execution history"):
        async with identity_engine.begin() as connection:
            await connection.run_sync(run_revision_step, "0023_profile_access_origin", "downgrade")
    async with async_sessionmaker(identity_engine)() as session:
        retained = await session.get(ProfileAccessRecord, result.access_context.id)
        assert retained is not None
        assert retained.request_id == origin.request_id


@pytest.mark.parametrize("malformed", ["orphan_action", "partial_trace", "zero_trace"])
async def test_database_rejects_malformed_disclosure_origin(
    identity_engine: AsyncEngine, malformed: str
) -> None:
    _, _, context = await prepared(identity_engine)
    values: dict[str, object]
    if malformed == "orphan_action":
        values = {"action_id": uuid4()}
    elif malformed == "partial_trace":
        values = {"request_id": uuid4(), "trace_id": "a" * 32}
    else:
        values = {"request_id": uuid4(), "trace_id": "0" * 32, "span_id": "b" * 16}
    with pytest.raises(IntegrityError):
        async with async_sessionmaker(identity_engine).begin() as session:
            await session.execute(
                update(ProfileAccessRecord)
                .where(ProfileAccessRecord.id == context.id)
                .values(**values)
            )
