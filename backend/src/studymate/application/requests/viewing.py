"""Explicit viewed acknowledgement; opening a detail is never acknowledgement."""

import hmac
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID, uuid4

from studymate.application.idempotency import (
    IdempotencyConflictError,
    IntentFingerprinter,
    IntentKey,
)
from studymate.application.identity.sessions import (
    IdentityReader,
    SessionCredential,
    SessionHasher,
    StudentActionDeniedError,
    UnauthenticatedError,
    require_verified_student,
)
from studymate.domain.requests.states import RequestUnavailableError
from studymate.domain.requests.views import RequestDisclosure, RequestViewReceipt


@dataclass(frozen=True, slots=True)
class ViewRequestCommand:
    credential: SessionCredential
    request_id: UUID
    disclosure_id: UUID
    key: IntentKey


@dataclass(frozen=True, slots=True)
class RequestViewIntent:
    fingerprint: bytes = field(repr=False)
    receipt: RequestViewReceipt


class RequestViewTransaction(IdentityReader, Protocol):
    async def disclosure(
        self, viewer_id: UUID, request_id: UUID, disclosure_id: UUID
    ) -> RequestDisclosure | None:
        """Filter all three owned source fields before returning retained content."""
        ...

    async def view_intent(self, actor_id: UUID, key: IntentKey) -> RequestViewIntent | None: ...

    async def acknowledge(self, source: RequestViewReceipt) -> RequestViewReceipt:
        """Insert once per viewer/request/sourceversion; return original on deduplication."""
        ...

    async def remember_view(
        self, actor_id: UUID, key: IntentKey, intent: RequestViewIntent, at: datetime
    ) -> None: ...


class RequestViewUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[RequestViewTransaction]: ...


@dataclass(frozen=True, slots=True)
class AcknowledgeRequestViewed:
    unit_of_work: RequestViewUnitOfWork
    hasher: SessionHasher
    fingerprinter: IntentFingerprinter

    async def __call__(self, command: ViewRequestCommand) -> RequestViewReceipt:
        async with self.unit_of_work.transaction() as transaction:
            actor, _ = await require_verified_student(
                transaction, await self.hasher.digest(command.credential)
            )
            if not actor.activation_complete:
                raise StudentActionDeniedError
            actor_id = actor.session.account_id
            fingerprint = await self.fingerprinter.fingerprint(
                (
                    "requests.viewed.v1",
                    str(actor_id),
                    str(command.request_id),
                    str(command.disclosure_id),
                )
            )
            prior = await transaction.view_intent(actor_id, command.key)
            if prior is not None:
                if not hmac.compare_digest(prior.fingerprint, fingerprint):
                    raise IdempotencyConflictError
                return prior.receipt
            source = await transaction.disclosure(
                actor_id, command.request_id, command.disclosure_id
            )
            if source is None:
                raise RequestUnavailableError
            if (source.viewer_id, source.request_id, source.id) != (
                actor_id,
                command.request_id,
                command.disclosure_id,
            ):
                raise RuntimeError("Request disclosure returned another owned source")
            receipt = await transaction.acknowledge(
                RequestViewReceipt(
                    uuid4(),
                    actor_id,
                    source.request_id,
                    source.stored_version,
                    source.id,
                    await transaction.now(),
                )
            )
            if (receipt.viewer_id, receipt.request_id, receipt.stored_version) != (
                actor_id,
                source.request_id,
                source.stored_version,
            ):
                raise RuntimeError("View acknowledgement returned another owned source")
            now = await transaction.now()
            await transaction.remember_view(
                actor_id, command.key, RequestViewIntent(fingerprint, receipt), now
            )
            if not actor.session.is_active(await transaction.now()):
                raise UnauthenticatedError
            return receipt
