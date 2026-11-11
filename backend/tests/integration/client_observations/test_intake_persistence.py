"""Real migrated intake: concurrency, history and transaction-scoped rate admission."""

import asyncio
from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.client_observations.intake import (
    AcceptClientObservations,
    ObservationActorChangedError,
    ObservationBatchCommand,
    ObservationRateLimitError,
)
from studymate.application.idempotency import IntentKey
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.domain.client_observations.catalogue import QualityReason, Screen
from studymate.domain.client_observations.events import ObservationHeader, QualityObserved
from studymate.infrastructure.client_observations.models import (
    ClientObservationRecord,
    ObservationBatchRecord,
)
from studymate.infrastructure.client_observations.persistence import SqlObservationIntakeUnitOfWork
from studymate.infrastructure.external_delivery.materialization import database_now
from studymate.infrastructure.external_delivery.models import DeliverySourceRecord
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.integration.student_actor import actor

pytestmark = pytest.mark.integration


class NoPublicFrames:
    def known_assets(self, release_id: str) -> frozenset[int] | None:
        return frozenset() if release_id else None


async def test_concurrent_exact_replay_one_source_and_all_metadata_survives_deletion(
    identity_engine: AsyncEngine,
) -> None:
    owner = await actor(identity_engine, verified=False)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    intake = AcceptClientObservations(
        SqlObservationIntakeUnitOfWork(sessions),
        Sha256SessionHasher(),
        HmacIntentFingerprinter(b"k" * 32),
        NoPublicFrames(),
    )
    async with sessions() as session:
        now = await database_now(session)
    event = QualityObserved(
        ObservationHeader(uuid4(), now, Screen.STUDY), QualityReason.EXHAUSTED, 2
    )
    command = ObservationBatchCommand(
        owner.credential, (event,), IntentKey("observation_key"), owner.id
    )
    first, replay = await asyncio.gather(intake(command), intake(command))
    assert first == replay
    assert first.accepted == (event.header.event_id,)
    with pytest.raises(ObservationActorChangedError):
        await intake(replace(command, expected_actor_id=uuid4()))
    async with sessions.begin() as session:
        assert await session.scalar(select(func.count()).select_from(ClientObservationRecord)) == 1
        assert await session.scalar(select(func.count()).select_from(ObservationBatchRecord)) == 1
        assert (
            await session.scalar(
                select(func.count())
                .select_from(DeliverySourceRecord)
                .where(DeliverySourceRecord.source_kind == "client_observation")
            )
            == 1
        )
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == owner.id)
            .values(deleted_at=func.clock_timestamp())
        )
    with pytest.raises(UnauthenticatedError):
        await intake(command)
    async with sessions() as session:
        retained = (await session.scalars(select(ClientObservationRecord))).one()
        assert retained.account_id == owner.id
        assert retained.quality_reason == QualityReason.EXHAUSTED.value
        assert retained.quality_count == event.count
        assert (await session.scalars(select(ObservationBatchRecord))).one().accepted_ids == [
            event.header.event_id
        ]


async def test_actor_rate_alias_keys_are_charged_but_exact_replay_is_free(
    identity_engine: AsyncEngine,
) -> None:
    owner = await actor(identity_engine, verified=False)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    intake = AcceptClientObservations(
        SqlObservationIntakeUnitOfWork(sessions),
        Sha256SessionHasher(),
        HmacIntentFingerprinter(b"k" * 32),
        NoPublicFrames(),
    )
    async with sessions() as session:
        now = await database_now(session)
    event = QualityObserved(
        ObservationHeader(uuid4(), now, Screen.PROFILE), QualityReason.OVERFLOW, 1
    )
    command = ObservationBatchCommand(
        owner.credential, (event,), IntentKey("observation_0"), owner.id
    )
    receipt = await intake(command)
    for number in range(1, 10):
        alias = await intake(replace(command, intent_key=IntentKey(f"observation_{number}")))
        assert alias.accepted == ()
        assert alias.duplicates == receipt.accepted
    with pytest.raises(ObservationRateLimitError):
        await intake(replace(command, intent_key=IntentKey("observation_10")))
    assert await intake(command) == receipt
