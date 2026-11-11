import hmac
import re
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
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
    UnauthenticatedError,
    require_session_identity,
)
from studymate.domain.support.cases import SupportContent, SupportReceipt, SupportStatus

PROOF_LIFETIME = timedelta(days=7)
SOURCE_WINDOW = timedelta(hours=24)
SOURCE_LIMIT = 5
PROOF_LIMIT = 5
RECENT_RECEIPT_LIMIT = 20


class SupportUnavailableError(Exception):
    pass


class SupportQuotaError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class SupportCredential:
    value: str = field(repr=False)

    def __post_init__(self) -> None:
        if re.fullmatch(r"[A-Za-z0-9_-]{43}", self.value) is None:
            raise SupportUnavailableError


class SupportProofs(Protocol):
    def issue(self) -> SupportCredential: ...

    def digest(self, credential: SupportCredential) -> bytes: ...


@dataclass(frozen=True, slots=True)
class SupportProof:
    digest: bytes = field(repr=False)
    source_digest: bytes = field(repr=False)
    created_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class SupportIntent:
    fingerprint: bytes = field(repr=False)
    receipt: SupportReceipt


@dataclass(frozen=True, slots=True)
class NewSupportCase:
    proof: SupportProof
    actor_id: UUID | None
    content: SupportContent
    receipt: SupportReceipt
    key: IntentKey
    fingerprint: bytes = field(repr=False)


class SupportTransaction(IdentityReader, Protocol):
    async def lock_proof(self, digest: bytes) -> SupportProof | None: ...

    async def create_proof(self, proof: SupportProof) -> None: ...

    async def admit_preparation(self, source_digest: bytes, at: datetime) -> None:
        """Serialize source quota; reject after 10 preparations per rolling hour."""
        ...

    async def intent(self, digest: bytes, key: IntentKey) -> SupportIntent | None: ...

    async def admit_case(self, proof: SupportProof, at: datetime) -> None:
        """Serialize source quota; at most 5/source/day and 5/proof total."""
        ...

    async def create_case(self, case: NewSupportCase) -> None: ...

    async def owned_receipt(self, digest: bytes, case_id: UUID) -> SupportReceipt | None: ...

    async def actor_receipt(self, actor_id: UUID, case_id: UUID) -> SupportReceipt | None: ...

    async def proof_receipts(self, digest: bytes) -> tuple[SupportReceipt, ...]: ...

    async def actor_receipts(self, actor_id: UUID) -> tuple[SupportReceipt, ...]: ...


class SupportUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[SupportTransaction]: ...


@dataclass(frozen=True, slots=True)
class PrepareSupport:
    unit_of_work: SupportUnitOfWork
    proofs: SupportProofs

    async def __call__(
        self, source_digest: bytes, existing: SupportCredential | None = None
    ) -> tuple[SupportCredential, datetime]:
        async with self.unit_of_work.transaction() as transaction:
            now = await transaction.now()
            if existing is not None:
                proof = await transaction.lock_proof(self.proofs.digest(existing))
                if proof is not None and proof.expires_at > now:
                    return existing, proof.expires_at
            await transaction.admit_preparation(source_digest, now)
            credential = self.proofs.issue()
            expiry = now + PROOF_LIFETIME
            await transaction.create_proof(
                SupportProof(self.proofs.digest(credential), source_digest, now, expiry)
            )
            return credential, expiry


@dataclass(frozen=True, slots=True)
class CreateSupportCommand:
    proof: SupportCredential = field(repr=False)
    content: SupportContent
    intent_key: IntentKey
    session: SessionCredential | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class CreateSupportCase:
    unit_of_work: SupportUnitOfWork
    proofs: SupportProofs
    hasher: SessionHasher
    fingerprinter: IntentFingerprinter

    async def __call__(self, command: CreateSupportCommand) -> SupportReceipt:
        content = command.content
        fingerprint = await self.fingerprinter.fingerprint(
            (
                "support.create.v1",
                content.topic.value,
                content.reply_address,
                content.message,
                "present" if content.details is not None else "absent",
                content.details or "",
            )
        )
        async with self.unit_of_work.transaction() as transaction:
            actor_id = None
            if command.session is not None:
                actor, _ = await require_session_identity(
                    transaction, await self.hasher.digest(command.session)
                )
                actor_id = actor.session.account_id
            digest = self.proofs.digest(command.proof)
            proof = await transaction.lock_proof(digest)
            now = await transaction.now()
            if proof is None or proof.expires_at <= now:
                raise SupportUnavailableError
            prior = await transaction.intent(digest, command.intent_key)
            if prior is not None:
                if not hmac.compare_digest(prior.fingerprint, fingerprint):
                    raise IdempotencyConflictError
                if proof.expires_at <= await transaction.now():
                    raise SupportUnavailableError
                if command.session is not None and not actor.session.is_active(
                    await transaction.now()
                ):
                    raise UnauthenticatedError
                return prior.receipt
            await transaction.admit_case(proof, now)
            now = await transaction.now()
            receipt = SupportReceipt(uuid4(), SupportStatus.RECEIVED, 1, now, now)
            await transaction.create_case(
                NewSupportCase(proof, actor_id, content, receipt, command.intent_key, fingerprint)
            )
            if proof.expires_at <= await transaction.now():
                raise SupportUnavailableError
            if command.session is not None and not actor.session.is_active(await transaction.now()):
                raise UnauthenticatedError
            return receipt


@dataclass(frozen=True, slots=True)
class ReadSupportCase:
    unit_of_work: SupportUnitOfWork
    proofs: SupportProofs

    async def __call__(self, credential: SupportCredential, case_id: UUID) -> SupportReceipt:
        async with self.unit_of_work.transaction() as transaction:
            digest = self.proofs.digest(credential)
            proof = await transaction.lock_proof(digest)
            if proof is None or proof.expires_at <= await transaction.now():
                raise SupportUnavailableError
            receipt = await transaction.owned_receipt(digest, case_id)
            if receipt is None or proof.expires_at <= await transaction.now():
                raise SupportUnavailableError
            return receipt


@dataclass(frozen=True, slots=True)
class ReadActorSupportCase:
    unit_of_work: SupportUnitOfWork
    hasher: SessionHasher

    async def __call__(self, credential: SessionCredential, case_id: UUID) -> SupportReceipt:
        async with self.unit_of_work.transaction() as transaction:
            identity, _ = await require_session_identity(
                transaction, await self.hasher.digest(credential)
            )
            result = await transaction.actor_receipt(identity.session.account_id, case_id)
            if result is None:
                raise SupportUnavailableError
            if not identity.session.is_active(await transaction.now()):
                raise UnauthenticatedError
            return result


@dataclass(frozen=True, slots=True)
class ReadRecentSupportCases:
    unit_of_work: SupportUnitOfWork
    proofs: SupportProofs

    async def __call__(self, credential: SupportCredential) -> tuple[SupportReceipt, ...]:
        async with self.unit_of_work.transaction() as transaction:
            digest = self.proofs.digest(credential)
            proof = await transaction.lock_proof(digest)
            if proof is None or proof.expires_at <= await transaction.now():
                raise SupportUnavailableError
            result = await transaction.proof_receipts(digest)
            if proof.expires_at <= await transaction.now():
                raise SupportUnavailableError
            return result


@dataclass(frozen=True, slots=True)
class ReadRecentActorSupportCases:
    unit_of_work: SupportUnitOfWork
    hasher: SessionHasher

    async def __call__(self, credential: SessionCredential) -> tuple[SupportReceipt, ...]:
        async with self.unit_of_work.transaction() as transaction:
            identity, _ = await require_session_identity(
                transaction, await self.hasher.digest(credential)
            )
            result = await transaction.actor_receipts(identity.session.account_id)
            if not identity.session.is_active(await transaction.now()):
                raise UnauthenticatedError
            return result
