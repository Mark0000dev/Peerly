from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.sessions import (
    IdentitySnapshot,
    SessionCredential,
    UnauthenticatedError,
)
from studymate.application.support.cases import (
    CreateSupportCase,
    CreateSupportCommand,
    NewSupportCase,
    PrepareSupport,
    ReadActorSupportCase,
    ReadSupportCase,
    SupportIntent,
    SupportProof,
    SupportQuotaError,
    SupportTransaction,
    SupportUnavailableError,
)
from studymate.domain.identity import Session
from studymate.domain.support.cases import SupportContent, SupportReceipt, SupportTopic
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.support.proofs import OpaqueSupportProofs

NOW = datetime(2026, 11, 9, tzinfo=UTC)
SESSION = SessionCredential("a" * 43)


class Hasher:
    async def digest(self, credential: SessionCredential) -> bytes:
        return credential.value.encode()


class Store:
    def __init__(self) -> None:
        self.clock = NOW
        self.proofs: dict[bytes, SupportProof] = {}
        self.intents: dict[tuple[bytes, IntentKey], SupportIntent] = {}
        self.cases: dict[UUID, NewSupportCase] = {}
        self.actor_id = uuid4()
        self.deleted = False
        self.expired_session = False
        self.exhausted = False
        self.preparations = 0
        self.admissions = 0

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SupportTransaction]:
        yield self

    def authenticated(self, account_id: UUID) -> None:
        assert account_id == self.actor_id

    async def lock_identity(self, secret_digest: bytes) -> IdentitySnapshot:
        assert secret_digest == SESSION.value.encode()
        expiry = NOW if self.expired_session else NOW + timedelta(days=1)
        return IdentitySnapshot(
            Session(uuid4(), self.actor_id, NOW - timedelta(hours=1), expiry, None),
            None,
            True,
            deleted_at=NOW if self.deleted else None,
        )

    async def now(self) -> datetime:
        return self.clock

    async def lock_proof(self, digest: bytes) -> SupportProof | None:
        return self.proofs.get(digest)

    async def create_proof(self, proof: SupportProof) -> None:
        self.proofs[proof.digest] = proof

    async def admit_preparation(self, source_digest: bytes, at: datetime) -> None:
        assert source_digest == b"s" * 32
        assert at == self.clock
        self.preparations += 1
        if self.exhausted:
            raise SupportQuotaError

    async def intent(self, digest: bytes, key: IntentKey) -> SupportIntent | None:
        return self.intents.get((digest, key))

    async def admit_case(self, proof: SupportProof, at: datetime) -> None:
        assert proof.digest in self.proofs
        assert at == self.clock
        self.admissions += 1
        if self.exhausted:
            raise SupportQuotaError

    async def create_case(self, case: NewSupportCase) -> None:
        self.cases[case.receipt.case_id] = case
        self.intents[(case.proof.digest, case.key)] = SupportIntent(case.fingerprint, case.receipt)

    async def owned_receipt(self, digest: bytes, case_id: UUID) -> SupportReceipt | None:
        case = self.cases.get(case_id)
        return case.receipt if case is not None and case.proof.digest == digest else None

    async def proof_receipts(self, digest: bytes) -> tuple[SupportReceipt, ...]:
        return tuple(case.receipt for case in self.cases.values() if case.proof.digest == digest)

    async def actor_receipts(self, actor_id: UUID) -> tuple[SupportReceipt, ...]:
        return tuple(case.receipt for case in self.cases.values() if case.actor_id == actor_id)

    async def actor_receipt(self, actor_id: UUID, case_id: UUID) -> SupportReceipt | None:
        case = self.cases.get(case_id)
        return case.receipt if case is not None and case.actor_id == actor_id else None


async def test_banned_unverified_actor_can_request_help_but_deleted_identity_cannot_bind() -> None:
    store = Store()
    proofs = OpaqueSupportProofs()
    prepare = PrepareSupport(store, proofs)
    proof, expiry = await prepare(b"s" * 32)
    assert await prepare(b"s" * 32, proof) == (proof, expiry)
    assert store.preparations == 1
    create = CreateSupportCase(store, proofs, Hasher(), HmacIntentFingerprinter(b"k" * 32))
    content = SupportContent(SupportTopic.CANNOT_SIGN_IN, "reply@example.test", "Cannot sign in")
    command = CreateSupportCommand(proof, content, IntentKey("support_001"), SESSION)
    result = await create(command)
    assert await ReadActorSupportCase(store, Hasher())(SESSION, result.case_id) == result
    assert await ReadSupportCase(store, proofs)(proof, result.case_id) == result
    store.exhausted = True
    assert await create(command) == result
    assert store.admissions == 1
    with pytest.raises(IdempotencyConflictError):
        await create(
            CreateSupportCommand(
                proof,
                SupportContent(SupportTopic.OTHER, "reply@example.test", "Other problem"),
                command.intent_key,
                SESSION,
            )
        )
    store.deleted = True
    with pytest.raises(UnauthenticatedError):
        await create(command)
    with pytest.raises(UnauthenticatedError):
        await ReadActorSupportCase(store, Hasher())(SESSION, result.case_id)
    # The retained proof still grants only its narrow support receipt after deletion.
    assert await ReadSupportCase(store, proofs)(proof, result.case_id) == result


async def test_missing_foreign_expired_proofs_and_cases_share_unavailable_outcome() -> None:
    store = Store()
    proofs = OpaqueSupportProofs()
    prepare = PrepareSupport(store, proofs)
    proof, expiry = await prepare(b"s" * 32)
    create = CreateSupportCase(store, proofs, Hasher(), HmacIntentFingerprinter(b"k" * 32))
    command = CreateSupportCommand(
        proof,
        SupportContent(SupportTopic.DELETED_ACCOUNT, "reply@example.test", "Cannot sign in"),
        IntentKey("support_001"),
    )
    result = await create(command)
    foreign, _ = await prepare(b"s" * 32)
    read = ReadSupportCase(store, proofs)
    for credential, case_id in (
        (proofs.issue(), result.case_id),
        (foreign, result.case_id),
        (proof, uuid4()),
    ):
        with pytest.raises(SupportUnavailableError):
            await read(credential, case_id)
    with pytest.raises(SupportUnavailableError):
        await ReadActorSupportCase(store, Hasher())(SESSION, result.case_id)
    store.clock = expiry
    with pytest.raises(SupportUnavailableError):
        await create(command)
    with pytest.raises(SupportUnavailableError):
        await read(proof, result.case_id)
    renewed, _ = await prepare(b"s" * 32, proof)
    assert renewed != proof
    store.exhausted = True
    with pytest.raises(SupportQuotaError):
        await prepare(b"s" * 32)
    with pytest.raises(SupportQuotaError):
        await create(CreateSupportCommand(renewed, command.content, IntentKey("support_002")))
