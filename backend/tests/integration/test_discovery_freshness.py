from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.identity.sessions import StudentActionDeniedError, UnauthenticatedError
from studymate.application.profiles.basics import SaveOwnProfile, SaveProfileCommand
from studymate.domain.membership import GOOGLE_ISSUER
from studymate.domain.profiles import DisplayName, OnboardingTask, ProfileBasics
from studymate.infrastructure.persistence.discovery_freshness_models import (
    DiscoveryExposureRecord,
    DiscoveryFreshnessPolicyRecord,
)
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    ExternalIdentityRecord,
    SessionRecord,
)
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityTransaction
from studymate.infrastructure.persistence.onboarding_models import (
    VisibilityIntentRecord,
    VisibilityRevisionRecord,
)
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.profiles import SqlProfileUnitOfWork
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from studymate.presentation.identity import IdentityResponse
from studymate.presentation.onboarding_models import OnboardingStatusResponse
from tests.integration.http_identity import BrowserHarness, login, write_headers
from tests.integration.legacy_freshness_fixture import prepare_legacy_freshness
from tests.integration.migrations import migrate
from tests.integration.profile_lifecycle_fixture import activated, command, services

pytestmark = pytest.mark.integration


async def advance(
    engine: AsyncEngine,
    account_id: UUID,
    monkeypatch: pytest.MonkeyPatch,
    *,
    days: int = 31,
) -> datetime:
    future = datetime.now(UTC) + timedelta(days=days)
    async with async_sessionmaker(engine).begin() as session:
        await session.execute(
            update(SessionRecord)
            .where(SessionRecord.account_id == account_id)
            .values(expires_at=future + timedelta(days=7))
        )

    async def clock(_transaction: SqlIdentityTransaction) -> datetime:
        return future

    monkeypatch.setattr(SqlIdentityTransaction, "now", clock)
    return future


async def test_background_reads_expose_pause_without_warming_activity_or_revoking_contact(
    identity_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = await activated(identity_engine)
    _, status = services(identity_engine)
    initial = await status(owner.credential)
    assert initial.discovery_exposure is not None
    assert not initial.discovery_exposure.paused
    async with async_sessionmaker(identity_engine)() as session:
        source = await session.get(DiscoveryExposureRecord, owner.id)
        assert source is not None
        original_activity = source.last_activity_at
    await advance(identity_engine, owner.id, monkeypatch)
    first, repeated = await status(owner.credential), await status(owner.credential)
    assert first == repeated
    assert first.discovery_exposure is not None
    assert first.discovery_exposure.paused
    assert first.discovery_exposure.can_confirm
    assert first.capabilities.can_discover
    assert first.capabilities.can_make_new_contacts
    assert first.capabilities.can_access_existing_chats
    async with async_sessionmaker(identity_engine)() as session:
        source = await session.get(DiscoveryExposureRecord, owner.id)
        assert source is not None
        assert source.last_activity_at == original_activity
        assert source.paused_at is None


async def test_foreground_profile_action_materializes_pause_before_warming_its_source(
    identity_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = await activated(identity_engine)
    at = await advance(identity_engine, owner.id, monkeypatch)
    await SaveOwnProfile(
        SqlProfileUnitOfWork(async_sessionmaker(identity_engine, expire_on_commit=False)),
        Sha256SessionHasher(),
        HmacIntentFingerprinter(bytes(range(32))),
    )(
        SaveProfileCommand(
            owner.credential,
            ProfileBasics(DisplayName("Updated synthetic name")),
            OnboardingTask.FIND_HELP,
            1,
            command(owner).intent_key,
        )
    )
    _, status = services(identity_engine)
    result = await status(owner.credential)
    assert result.discovery_exposure is not None
    assert result.discovery_exposure.paused
    async with async_sessionmaker(identity_engine)() as session:
        source = await session.get(DiscoveryExposureRecord, owner.id)
        assert source is not None
        assert source.last_activity_at == at
        assert source.paused_at is not None
        assert source.paused_at < source.last_activity_at
        assert source.confirmed_at < source.paused_at


async def test_visible_explicit_confirmation_has_own_fact_but_no_fake_visibility_revision(
    identity_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = await activated(identity_engine)
    change, status = services(identity_engine)
    at = await advance(identity_engine, owner.id, monkeypatch)
    submitted = command(owner, hidden=False)
    result = await change(submitted)
    assert result.visibility_version == 1
    assert not result.hidden
    assert await change(submitted) == result
    current = await status(owner.credential)
    assert current.discovery_exposure is not None
    assert not current.discovery_exposure.paused
    async with async_sessionmaker(identity_engine)() as session:
        source = await session.get(DiscoveryExposureRecord, owner.id)
        intent = await session.get(VisibilityIntentRecord, (owner.id, submitted.intent_key.value))
        assert source is not None
        assert intent is not None
        assert source.confirmed_at == at
        assert source.confirmation_key == submitted.intent_key.value
        assert intent.confirmed_exposure_at == at
        assert intent.previous_exposure_paused_at is not None
        assert (
            await session.scalars(select(func.count()).select_from(VisibilityRevisionRecord))
        ).one() == 1
        assert (
            await session.scalars(
                select(ProductEventRecord.kind).where(
                    ProductEventRecord.kind.in_(("profile.hidden", "profile.restored"))
                )
            )
        ).all() == []
    await advance(identity_engine, owner.id, monkeypatch, days=62)
    assert await change(submitted) == result
    later = await status(owner.credential)
    assert later.discovery_exposure is not None
    assert later.discovery_exposure.paused
    assert later.discovery_exposure.can_confirm


async def test_manual_hide_remains_dominant_and_actual_restore_is_explicit(
    identity_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = await activated(identity_engine)
    change, status = services(identity_engine)
    hidden = await change(command(owner))
    await advance(identity_engine, owner.id, monkeypatch)
    current = await status(owner.credential)
    assert current.discovery_exposure is not None
    assert current.discovery_exposure.paused
    assert not current.discovery_exposure.can_confirm
    assert current.capabilities.can_access_existing_chats
    restored = await change(command(owner, hidden=False, version=hidden.visibility_version))
    assert not restored.hidden
    assert restored.visibility_version == hidden.visibility_version + 1
    actual = await status(owner.credential)
    assert actual.discovery_exposure is not None
    assert not actual.discovery_exposure.paused


@pytest.mark.parametrize("state", ["banned", "deleted"])
async def test_paused_exposure_cannot_override_a_ban_or_deletion(
    identity_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    state: str,
) -> None:
    owner = await activated(identity_engine)
    at = await advance(identity_engine, owner.id, monkeypatch)
    async with async_sessionmaker(identity_engine).begin() as session:
        column = AccountRecord.banned_at if state == "banned" else AccountRecord.deleted_at
        await session.execute(
            update(AccountRecord).where(AccountRecord.id == owner.id).values({column: at})
        )
    change, _ = services(identity_engine)
    with pytest.raises(UnauthenticatedError if state == "deleted" else StudentActionDeniedError):
        await change(command(owner, hidden=False))
    async with async_sessionmaker(identity_engine)() as session:
        source = await session.get(DiscoveryExposureRecord, owner.id)
        assert source is not None
        assert source.last_activity_at < at
        assert source.confirmation_key is None


async def test_legacy_backfill_uses_actual_sources_without_creating_confirmation_or_events(
    identity_engine: AsyncEngine,
) -> None:
    owner = await activated(identity_engine)
    sessions = async_sessionmaker(identity_engine)
    async with sessions() as session:
        source = await session.get(DiscoveryExposureRecord, owner.id)
        assert source is not None
        original = (source.last_activity_at, source.confirmed_at, source.paused_at)
        events = (await session.scalars(select(func.count()).select_from(ProductEventRecord))).one()

    # Build actual18 in a separate savepoint-owned schema. Current42+ canonical
    # sources stay intact; old CHECKs must never be installed over newer facts.
    async with identity_engine.begin() as connection:
        savepoint = await connection.begin_nested()
        try:
            legacy_events = await connection.run_sync(prepare_legacy_freshness)
            await connection.run_sync(migrate, "0019_discovery_freshness")
            restored = (
                await connection.execute(
                    select(
                        DiscoveryExposureRecord.last_activity_at,
                        DiscoveryExposureRecord.confirmed_at,
                        DiscoveryExposureRecord.paused_at,
                        DiscoveryExposureRecord.confirmation_key,
                    ).where(DiscoveryExposureRecord.account_id == owner.id)
                )
            ).one()
            assert (restored[0], restored[1], restored[2]) == original
            assert restored[3] is None
            assert (
                await connection.scalar(select(func.count()).select_from(ProductEventRecord))
                == legacy_events
            )
            assert (
                await connection.scalar(select(func.count()).select_from(VisibilityIntentRecord))
                == 0
            )
        finally:
            await savepoint.rollback()
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(ProductEventRecord)) == events

    async with sessions() as session:
        retained = await session.get(DiscoveryExposureRecord, owner.id)
        assert retained is not None
        assert (retained.last_activity_at, retained.confirmed_at, retained.paused_at) == original


async def test_google_return_and_background_http_do_not_confirm_expired_exposure(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = await activated(identity_engine)
    async with async_sessionmaker(identity_engine).begin() as session:
        session.add(
            ExternalIdentityRecord(
                id=uuid4(),
                account_id=owner.id,
                issuer=GOOGLE_ISSUER,
                subject="subject",
                created_at=datetime.now(UTC),
            )
        )
    first_return = await advance(identity_engine, owner.id, monkeypatch)
    await login(browser.client)
    identity = IdentityResponse.model_validate((await browser.client.get("/api/v1/me")).json())
    assert identity.account_id == owner.id
    assert identity.capabilities.can_use_student_features
    async with async_sessionmaker(identity_engine)() as session:
        source = await session.get(DiscoveryExposureRecord, owner.id)
        assert source is not None
        assert source.last_activity_at == first_return
        pause = source.paused_at
        assert pause is not None
        assert source.confirmation_key is None
    await advance(identity_engine, owner.id, monkeypatch, days=32)
    client = browser.client
    for path in ("/api/v1/me", "/api/v1/me/profile", "/api/v1/me/onboarding"):
        assert (await client.get(path)).status_code == HTTPStatus.OK
    current = OnboardingStatusResponse.model_validate(
        (await client.get("/api/v1/me/onboarding")).json()
    )
    assert current.discovery_exposure is not None
    assert current.discovery_exposure.paused
    assert current.discovery_exposure.can_confirm
    assert current.discovery_exposure.requirements == ()
    assert current.capabilities.can_make_new_contacts
    assert current.capabilities.can_access_existing_chats
    async with async_sessionmaker(identity_engine)() as session:
        source = await session.get(DiscoveryExposureRecord, owner.id)
        assert source is not None
        assert source.last_activity_at == first_return
        assert source.paused_at == pause
    headers = await write_headers(client)
    confirmed = await client.put(
        "/api/v1/me/visibility", json={"hidden": False, "expected_version": 1}, headers=headers
    )
    assert confirmed.status_code == HTTPStatus.OK
    assert confirmed.json()["version"] == 1
    assert (
        await client.put(
            "/api/v1/me/visibility", json={"hidden": False, "expected_version": 1}, headers=headers
        )
    ).json() == confirmed.json()
    actual = OnboardingStatusResponse.model_validate(
        (await client.get("/api/v1/me/onboarding")).json()
    )
    assert actual.discovery_exposure is not None
    assert not actual.discovery_exposure.paused
    assert actual.visibility is not None
    assert actual.visibility.version == 1


async def test_policy_change_preserves_expired_source_until_explicit_confirmation(
    identity_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = await activated(identity_engine)
    at = await advance(identity_engine, owner.id, monkeypatch)
    window = timedelta(days=60)
    async with async_sessionmaker(identity_engine).begin() as session:
        session.add(
            DiscoveryFreshnessPolicyRecord(
                version=2,
                inactivity_seconds=int(window.total_seconds()),
                published_at=at,
            )
        )
    change, status = services(identity_engine)
    current = await status(owner.credential)
    assert current.discovery_exposure is not None
    assert current.discovery_exposure.paused
    await change(command(owner, hidden=False))
    confirmed = await status(owner.credential)
    assert confirmed.discovery_exposure is not None
    assert not confirmed.discovery_exposure.paused
    async with async_sessionmaker(identity_engine)() as session:
        source = await session.get(DiscoveryExposureRecord, owner.id)
        assert source is not None
        assert source.inactivity_seconds == int(window.total_seconds())
        events = (
            await session.scalars(
                select(ProductEventRecord).where(
                    ProductEventRecord.kind == "discovery.exposure_confirmed"
                )
            )
        ).all()
        assert len(events) == 1
        assert events[0].occurred_at == at
        assert events[0].visibility_version == 1
