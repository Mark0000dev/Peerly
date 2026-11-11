"""Semantic intake fences/dedupe are observable outcomes, not persistence call counts."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from studymate.application.client_observations.intake import (
    BATCHES_PER_MINUTE,
    AcceptClientObservations,
    ObservationActorChangedError,
    ObservationAdmission,
    ObservationAssetError,
    ObservationBatchCommand,
    ObservationBatchIntent,
    ObservationRateLimitError,
    ObservationTimeError,
    StoredObservation,
)
from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.sessions import (
    IdentitySnapshot,
    SessionCredential,
    UnauthenticatedError,
)
from studymate.domain.client_observations.catalogue import ErrorCategory, Screen
from studymate.domain.client_observations.events import (
    ErrorObserved,
    ObservationHeader,
    PublicFrame,
    ScreenViewed,
)
from studymate.domain.identity import Session
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher

NOW = datetime(2026, 11, 10, tzinfo=UTC)
ACTOR = UUID(int=101)
CREDENTIAL = SessionCredential("a" * 43)


class IntakeStore:
    def __init__(self) -> None:
        self.identity = IdentitySnapshot(
            Session(uuid4(), ACTOR, NOW - timedelta(hours=1), NOW + timedelta(days=1)), None, False
        )
        self.batches: dict[tuple[UUID, str], ObservationBatchIntent] = {}
        self.events: dict[tuple[UUID, UUID], StoredObservation] = {}
        self.current_time = NOW
        self.quota = BATCHES_PER_MINUTE
        self.expire_on_save = False

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator["IntakeStore"]:
        batches, events, quota = self.batches.copy(), self.events.copy(), self.quota
        try:
            yield self
        except BaseException:
            self.batches, self.events, self.quota = batches, events, quota
            raise

    async def lock_identity(self, secret_digest: bytes) -> IdentitySnapshot:
        assert secret_digest
        return self.identity

    def authenticated(self, account_id: UUID) -> None:
        assert account_id == ACTOR

    async def now(self) -> datetime:
        return self.current_time

    async def prior_batch(self, actor_id: UUID, key: IntentKey) -> ObservationBatchIntent | None:
        return self.batches.get((actor_id, key.value))

    async def observations(
        self, actor_id: UUID, event_ids: tuple[UUID, ...]
    ) -> tuple[StoredObservation, ...]:
        return tuple(
            row
            for identifier in event_ids
            if (row := self.events.get((actor_id, identifier))) is not None
        )

    async def admit_batch(self, actor_id: UUID, at: datetime) -> None:
        assert actor_id == ACTOR
        assert at == self.current_time
        if not self.quota:
            raise ObservationRateLimitError(60)
        self.quota -= 1

    async def save_batch(self, actor_id: UUID, admission: ObservationAdmission) -> None:
        self.batches[(actor_id, admission.intent_key.value)] = admission.intent
        for row in admission.events:
            self.events[(actor_id, row.event.header.event_id)] = StoredObservation(
                actor_id, row.event.header.event_id, row.fingerprint
            )
        if self.expire_on_save:
            self.current_time = self.identity.session.expires_at

    def known_assets(self, release_id: str) -> frozenset[int] | None:
        return frozenset({0}) if release_id == "a" * 40 else None


def accept(store: IntakeStore) -> AcceptClientObservations:
    return AcceptClientObservations(
        store, Sha256SessionHasher(), HmacIntentFingerprinter(b"k" * 32), store
    )


def command(key: str = "batch_key_1") -> ObservationBatchCommand:
    event = ScreenViewed(ObservationHeader(uuid4(), NOW, Screen.STUDY))
    return ObservationBatchCommand(CREDENTIAL, (event,), IntentKey(key), ACTOR)


async def test_exact_retry_keeps_receipt_without_quota_and_alias_is_duplicate() -> None:
    store = IntakeStore()
    usecase, submitted = accept(store), command()
    receipt = await usecase(submitted)
    store.current_time += timedelta(minutes=2)
    store.quota = 0
    assert await usecase(submitted) == receipt
    store.quota = 1
    alias = await usecase(replace(submitted, intent_key=IntentKey("batch_key_2")))
    assert alias.accepted == ()
    assert alias.duplicates == receipt.accepted
    assert len(store.events) == 1


async def test_actor_fence_precedes_replay_and_deleted_identity_never_ingests() -> None:
    store = IntakeStore()
    submitted = command()
    await accept(store)(submitted)
    with pytest.raises(ObservationActorChangedError):
        await accept(store)(replace(submitted, expected_actor_id=uuid4()))
    store.identity = replace(store.identity, deleted_at=NOW)
    with pytest.raises(UnauthenticatedError):
        await accept(store)(submitted)
    assert len(store.events) == 1


async def test_conflict_and_late_session_failure_rollback_new_records_and_quota() -> None:
    store = IntakeStore()
    submitted = command()
    await accept(store)(submitted)
    changed = ScreenViewed(replace(submitted.events[0].header, screen=Screen.HELP))
    with pytest.raises(IdempotencyConflictError):
        await accept(store)(
            replace(submitted, events=(changed,), intent_key=IntentKey("batch_key_2"))
        )
    assert len(store.events) == len(store.batches) == 1
    store.expire_on_save = True
    before_quota = store.quota
    with pytest.raises(UnauthenticatedError):
        await accept(store)(command("batch_key_3"))
    assert len(store.events) == len(store.batches) == 1
    assert store.quota == before_quota


async def test_unknown_public_asset_and_untrusted_time_do_not_consume_quota() -> None:
    store = IntakeStore()
    submitted = command()
    error = ErrorObserved(
        submitted.events[0].header, ErrorCategory.JAVASCRIPT, (PublicFrame(1, 2, 3),)
    )
    with pytest.raises(ObservationAssetError):
        await accept(store)(replace(submitted, events=(error,), release_id="a" * 40))
    old = ScreenViewed(replace(submitted.events[0].header, observed_at=NOW - timedelta(days=2)))
    with pytest.raises(ObservationTimeError):
        await accept(store)(replace(submitted, events=(old,)))
    assert not store.events
    assert not store.batches
    assert store.quota == BATCHES_PER_MINUTE
