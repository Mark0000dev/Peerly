"""Only controlled local DB writes; no live staging grants/email/OTP consumption."""

from datetime import datetime
from uuid import UUID, uuid4

import pytest
from deployment.backend import manual_stage_verification as manual
from sqlalchemy import func, select, update
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from studymate.domain.identity import StudentEmail
from studymate.domain.membership import GOOGLE_ISSUER
from studymate.infrastructure.persistence.discovery_freshness_models import DiscoveryExposureRecord
from studymate.infrastructure.persistence.email_models import (
    EmailChallengeRecord,
    EmailDeliveryRecord,
)
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    ExternalIdentityRecord,
    InstitutionalBindingRecord,
)
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from tests.integration.student_actor import Actor, actor
from tests.integration.test_email_verification import services, start_command

pytestmark = pytest.mark.integration


async def owner(engine: AsyncEngine) -> Actor:
    value = await actor(engine, verified=False)
    async with async_sessionmaker(engine).begin() as session:
        at = await session.scalar(select(func.clock_timestamp()))
        session.add(
            ExternalIdentityRecord(
                id=uuid4(),
                account_id=value.id,
                issuer=GOOGLE_ISSUER,
                subject=value.id.hex,
                created_at=at,
            )
        )
    return value


def batch(*entries: manual.Entry) -> manual.Manifest:
    return manual.Manifest(
        uuid4(), "owner-approved-staging-quarantine", entries, "synthetic-manifest"
    )


async def call(
    engine: AsyncEngine, value: manual.Manifest, database_url: str, *, apply: bool
) -> dict[str, object]:
    database = make_url(database_url).database
    assert database is not None
    async with async_sessionmaker(engine, expire_on_commit=False).begin() as session:
        return await manual.execute(session, value, apply=apply, expected_database=database)


async def test_mixed_actual_write_replay_and_no_fake_otp_or_foreground(
    identity_engine: AsyncEngine, database_url: str
) -> None:
    real = await owner(identity_engine)
    synthetic = await owner(identity_engine)
    start, _ = services(identity_engine)
    email = StudentEmail("manual-real@mail.apu.edu.my")
    challenge = await start(start_command(real.credential, email))
    value = batch(
        manual.Entry(real.id, email.value, challenge.id),
        manual.Entry(synthetic.id, manual.placeholder(synthetic.id), None),
    )
    plan = await call(identity_engine, value, database_url, apply=False)
    assert plan["eligible"] == len(value.entries)
    async with async_sessionmaker(identity_engine)() as session:
        assert not tuple(await session.scalars(select(InstitutionalBindingRecord)))
        before = tuple(await session.scalars(select(DiscoveryExposureRecord.account_id)))
    applied = await call(identity_engine, value, database_url, apply=True)
    assert applied["applied"] == len(value.entries)
    assert applied["otp_consumed"] is False
    replay = await call(identity_engine, value, database_url, apply=True)
    assert replay["applied"] == 0
    assert replay["replayed"] == len(value.entries)
    assert replay["event_ids"] == applied["event_ids"]
    async with async_sessionmaker(identity_engine)() as session:
        bindings = tuple(await session.scalars(select(InstitutionalBindingRecord)))
        events = tuple(await session.scalars(select(ProductEventRecord)))
        assert {row.email for row in bindings} == {entry.email for entry in value.entries}
        assert len(events) == len(value.entries)
        assert {row.occurrence_key for row in events} == {
            manual.occurrence(value, entry) for entry in value.entries
        }
        assert all(row.request_id is None for row in events)
        source = await session.get(EmailChallengeRecord, challenge.id)
        assert source is not None
        assert source.consumed_at is None
        assert source.superseded_at is not None
        assert source.attempts == 0
        challenges = tuple(await session.scalars(select(EmailChallengeRecord)))
        assert len(challenges) == 1
        delivery = (await session.scalars(select(EmailDeliveryRecord))).one()
        assert delivery.status == "cancelled"
        assert delivery.sealed_envelope is None
        assert tuple(await session.scalars(select(DiscoveryExposureRecord.account_id))) == before


@pytest.mark.parametrize("restriction", ["banned", "deleted", "existing_challenge"])
async def test_restricted_or_false_placeholder_target_rejects_entire_batch(
    identity_engine: AsyncEngine, database_url: str, restriction: str
) -> None:
    first, second = await owner(identity_engine), await owner(identity_engine)
    if restriction == "existing_challenge":
        start, _ = services(identity_engine)
        await start(start_command(second.credential))
    else:
        async with async_sessionmaker(identity_engine).begin() as session:
            updates = (
                {"banned_at": func.clock_timestamp()}
                if restriction == "banned"
                else {"deleted_at": func.clock_timestamp()}
            )
            await session.execute(
                update(AccountRecord).where(AccountRecord.id == second.id).values(**updates)
            )
    value = batch(
        *(
            manual.Entry(person.id, manual.placeholder(person.id), None)
            for person in (first, second)
        )
    )
    with pytest.raises(manual.ManualVerificationError):
        await call(identity_engine, value, database_url, apply=True)
    async with async_sessionmaker(identity_engine)() as session:
        assert not tuple(await session.scalars(select(InstitutionalBindingRecord)))
        assert not tuple(await session.scalars(select(ProductEventRecord)))


async def test_actual_binding_and_event_roll_back_if_grant_fails_mid_batch(
    identity_engine: AsyncEngine, database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    first, second = await owner(identity_engine), await owner(identity_engine)
    value = batch(
        *(
            manual.Entry(person.id, manual.placeholder(person.id), None)
            for person in (first, second)
        )
    )
    original = manual.grant
    count = 0

    async def fail(
        session: AsyncSession, manifest: manual.Manifest, target: manual.Target, at: datetime
    ) -> UUID:
        nonlocal count
        count += 1
        result = await original(session, manifest, target, at)
        if count == len(value.entries):
            raise RuntimeError("synthetic post-write failure")
        return result

    monkeypatch.setattr(manual, "grant", fail)
    with pytest.raises(RuntimeError, match="synthetic post-write"):
        await call(identity_engine, value, database_url, apply=True)
    async with async_sessionmaker(identity_engine)() as session:
        assert not tuple(await session.scalars(select(InstitutionalBindingRecord)))
        assert not tuple(await session.scalars(select(ProductEventRecord)))
