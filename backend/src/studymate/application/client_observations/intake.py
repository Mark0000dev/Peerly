"""Atomic actual-actor intake. Observations remain untrusted after receipt."""

import hmac
import re
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID

from studymate.application.idempotency import (
    IdempotencyConflictError,
    IntentFingerprinter,
    IntentKey,
)
from studymate.application.identity.sessions import (
    IdentityReader,
    SessionCredential,
    SessionHasher,
    UnauthenticatedError,
    require_session_identity,
)
from studymate.domain.client_observations.events import MAX_EVENTS, ErrorObserved, Observation
from studymate.domain.time import require_aware

MAX_AGE = timedelta(hours=24)
MAX_FUTURE = timedelta(minutes=5)
BATCHES_PER_MINUTE = 10


class ObservationActorChangedError(Exception):
    pass


class ObservationTimeError(Exception):
    pass


class ObservationAssetError(Exception):
    pass


class ObservationRateLimitError(Exception):
    def __init__(self, retry_after: int) -> None:
        super().__init__("Client observation rate exceeded")
        self.retry_after = retry_after


@dataclass(frozen=True, slots=True)
class ObservationBatchCommand:
    credential: SessionCredential = field(repr=False)
    events: tuple[Observation, ...]
    intent_key: IntentKey
    expected_actor_id: UUID | None = None
    release_id: str | None = None

    def __post_init__(self) -> None:
        if not 1 <= len(self.events) <= MAX_EVENTS:
            raise ValueError("Observation batch requires1to20 semantic events")
        if len({event.header.event_id for event in self.events}) != len(self.events):
            raise ValueError("Observation batch cannot repeat an event identifier")
        if self.release_id is not None and re.fullmatch(r"[0-9a-f]{40}", self.release_id) is None:
            raise ValueError("Observation release requires its actual full source revision")


@dataclass(frozen=True, slots=True)
class ObservationBatchReceipt:
    accepted: tuple[UUID, ...]
    duplicates: tuple[UUID, ...]
    received_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.received_at)
        ids = (*self.accepted, *self.duplicates)
        if not 1 <= len(ids) <= MAX_EVENTS or len(set(ids)) != len(ids):
            raise ValueError("Observation receipt requires disjoint bounded actual event IDs")


@dataclass(frozen=True, slots=True)
class ObservationBatchIntent:
    fingerprint: bytes = field(repr=False)
    receipt: ObservationBatchReceipt


@dataclass(frozen=True, slots=True)
class StoredObservation:
    account_id: UUID
    event_id: UUID
    fingerprint: bytes = field(repr=False)


@dataclass(frozen=True, slots=True)
class AdmittedObservation:
    event: Observation
    fingerprint: bytes = field(repr=False)


@dataclass(frozen=True, slots=True)
class ObservationAdmission:
    intent_key: IntentKey
    intent: ObservationBatchIntent
    release_id: str | None
    events: tuple[AdmittedObservation, ...]


class PublicAssetRegistry(Protocol):
    def known_assets(self, release_id: str) -> frozenset[int] | None: ...


class ObservationIntakeTransaction(IdentityReader, Protocol):
    async def prior_batch(
        self, actor_id: UUID, key: IntentKey
    ) -> ObservationBatchIntent | None: ...

    async def observations(
        self, actor_id: UUID, event_ids: tuple[UUID, ...]
    ) -> tuple[StoredObservation, ...]: ...

    async def admit_batch(self, actor_id: UUID, at: datetime) -> None:
        """Actual account lock serializes at most10 new intent keys per rolling minute."""
        ...

    async def save_batch(self, actor_id: UUID, admission: ObservationAdmission) -> None:
        """Same transaction stores immutable receipt/events; source capture is DB infrastructure."""
        ...


class ObservationIntakeUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[ObservationIntakeTransaction]: ...


def validate_assets(
    events: tuple[Observation, ...], release: str | None, registry: PublicAssetRegistry
) -> None:
    frames = tuple(
        frame for event in events if isinstance(event, ErrorObserved) for frame in event.frames
    )
    if frames:
        assets = registry.known_assets(release) if release is not None else None
        if assets is None or any(frame.asset_id not in assets for frame in frames):
            raise ObservationAssetError


@dataclass(frozen=True, slots=True)
class AcceptClientObservations:
    unit_of_work: ObservationIntakeUnitOfWork
    hasher: SessionHasher
    fingerprinter: IntentFingerprinter
    assets: PublicAssetRegistry

    async def __call__(self, command: ObservationBatchCommand) -> ObservationBatchReceipt:
        release = command.release_id or ""
        fingerprints = tuple(
            [
                await self.fingerprinter.fingerprint(
                    ("client.observation.v1", release, *event.parts())
                )
                for event in command.events
            ]
        )
        fingerprint = await self.fingerprinter.fingerprint(
            (
                "client.observation-batch.v1",
                str(command.expected_actor_id or ""),
                release,
                *(value.hex() for value in fingerprints),
            )
        )
        async with self.unit_of_work.transaction() as transaction:
            identity, now = await require_session_identity(
                transaction, await self.hasher.digest(command.credential)
            )
            owner = identity.session.account_id
            if command.expected_actor_id is not None and command.expected_actor_id != owner:
                raise ObservationActorChangedError
            prior = await transaction.prior_batch(owner, command.intent_key)
            if prior is not None:
                if not hmac.compare_digest(prior.fingerprint, fingerprint):
                    raise IdempotencyConflictError
                result = prior.receipt
            else:
                validate_assets(command.events, command.release_id, self.assets)
                if any(
                    not now - MAX_AGE <= event.header.observed_at <= now + MAX_FUTURE
                    for event in command.events
                ):
                    raise ObservationTimeError
                ids = tuple(event.header.event_id for event in command.events)
                stored = await transaction.observations(owner, ids)
                existing = {row.event_id: row for row in stored}
                if len(existing) != len(stored) or any(
                    row.account_id != owner or row.event_id not in ids for row in stored
                ):
                    raise RuntimeError("Observation dedupe lost actual actor/event ownership")
                new_events: list[AdmittedObservation] = []
                duplicates: list[UUID] = []
                for event, digest in zip(command.events, fingerprints, strict=True):
                    old = existing.get(event.header.event_id)
                    if old is None:
                        new_events.append(AdmittedObservation(event, digest))
                    elif not hmac.compare_digest(old.fingerprint, digest):
                        raise IdempotencyConflictError
                    else:
                        duplicates.append(event.header.event_id)
                await transaction.admit_batch(owner, now)
                result = ObservationBatchReceipt(
                    tuple(row.event.header.event_id for row in new_events), tuple(duplicates), now
                )
                await transaction.save_batch(
                    owner,
                    ObservationAdmission(
                        command.intent_key,
                        ObservationBatchIntent(fingerprint, result),
                        command.release_id,
                        tuple(new_events),
                    ),
                )
            if not identity.session.is_active(await transaction.now()):
                raise UnauthenticatedError
            return result
