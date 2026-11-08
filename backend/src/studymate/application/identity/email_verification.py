"""Authenticated institutional membership commands; never a login mechanism."""

import hmac
import re
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol
from uuid import UUID, uuid4

from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.sessions import (
    IdentitySnapshot,
    IdentityTransaction,
    SessionCredential,
    SessionHasher,
    UnauthenticatedError,
    require_session_identity,
)
from studymate.domain.identity import StudentEmail
from studymate.domain.membership import (
    MAX_CODE_ATTEMPTS,
    AttemptOutcome,
    ChallengeState,
    EmailChallenge,
)


class EmailActionDeniedError(Exception):
    pass


class EmailChallengeUnavailableError(Exception):
    pass


class EmailRateLimitedError(Exception):
    def __init__(self, retry_at: datetime) -> None:
        super().__init__("Email challenge rate limited")
        self.retry_at = retry_at


@dataclass(frozen=True, slots=True)
class VerificationCode:
    value: str = field(repr=False)

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[0-9]{6}", self.value):
            raise ValueError("Verification code must contain six ASCII digits")


class EmailOperation(StrEnum):
    START = "start"
    VERIFY = "verify"


class VerificationOutcome(StrEnum):
    VERIFIED = "verified"
    WRONG = "wrong"
    LOCKED = "locked"
    EXPIRED = "expired"
    UNAVAILABLE = "unavailable"
    SUPPORT_REQUIRED = "support_required"


@dataclass(frozen=True, slots=True)
class ChallengeCreated:
    id: UUID
    expires_at: datetime
    resend_at: datetime


@dataclass(frozen=True, slots=True)
class VerificationResult:
    outcome: VerificationOutcome
    attempts_remaining: int
    verified_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class EmailIntent:
    fingerprint: bytes = field(repr=False)
    challenge_id: UUID
    result: VerificationResult | None


@dataclass(frozen=True, slots=True)
class StoredChallenge:
    challenge: EmailChallenge
    code_digest: bytes | None = field(repr=False)


@dataclass(frozen=True, slots=True)
class StartChallengeCommand:
    credential: SessionCredential = field(repr=False)
    email: StudentEmail
    intent_key: IntentKey
    source_digest: bytes = field(repr=False)
    resend_of: UUID | None = None


@dataclass(frozen=True, slots=True)
class VerifyChallengeCommand:
    credential: SessionCredential = field(repr=False)
    challenge_id: UUID
    code: VerificationCode = field(repr=False)
    intent_key: IntentKey


@dataclass(frozen=True, slots=True)
class EmailPolicy:
    deliveries_per_account: int = 5
    deliveries_per_address: int = 5
    starts_per_source: int = 30
    lifetime: timedelta = timedelta(minutes=10)
    resend_delay: timedelta = timedelta(seconds=30)


@dataclass(frozen=True, slots=True)
class DeliveryBudget:
    account: int
    address: int
    source: int
    account_reset: datetime | None = None
    address_reset: datetime | None = None
    source_reset: datetime | None = None

    def retry_at(self, policy: EmailPolicy, at: datetime) -> datetime | None:
        scopes = (
            (self.account, policy.deliveries_per_account, self.account_reset),
            (self.address, policy.deliveries_per_address, self.address_reset),
            (self.source, policy.starts_per_source, self.source_reset),
        )
        return max(
            (reset or at + timedelta(hours=1) for used, limit, reset in scopes if used >= limit),
            default=None,
        )


class EmailDeliveryState(StrEnum):
    QUEUED = "queued"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class ReadChallengeCommand:
    credential: SessionCredential = field(repr=False)
    challenge_id: UUID
    source_digest: bytes = field(repr=False)


@dataclass(frozen=True, slots=True)
class ChallengeStatus:
    id: UUID
    email: StudentEmail
    state: ChallengeState
    delivery: EmailDeliveryState
    verification_outcome: VerificationOutcome | None
    expires_at: datetime
    resend_at: datetime
    attempts_remaining: int
    can_verify: bool
    can_resend: bool


class EmailVault(Protocol):
    async def generate_code(self) -> VerificationCode: ...

    async def code_digest(self, challenge_id: UUID, code: VerificationCode) -> bytes: ...

    async def fingerprint(self, parts: tuple[str, ...]) -> bytes: ...

    async def seal_delivery(
        self, challenge_id: UUID, email: StudentEmail, code: VerificationCode
    ) -> bytes: ...


class EmailTransaction(IdentityTransaction, Protocol):
    async def intent(
        self, account_id: UUID, operation: EmailOperation, key: IntentKey
    ) -> EmailIntent | None: ...

    async def remember_intent(
        self, account_id: UUID, operation: EmailOperation, key: IntentKey, intent: EmailIntent
    ) -> None: ...

    async def lock_budget(
        self, account_id: UUID, email: StudentEmail, source: bytes, since: datetime
    ) -> DeliveryBudget: ...

    async def read_budget(
        self, account_id: UUID, email: StudentEmail, source: bytes, since: datetime
    ) -> DeliveryBudget: ...

    async def delivery_state(self, challenge_id: UUID) -> EmailDeliveryState: ...

    async def terminal_outcome(self, challenge_id: UUID) -> VerificationOutcome | None: ...

    async def current_challenge(self, account_id: UUID) -> StoredChallenge | None: ...

    async def lock_challenge(self, challenge_id: UUID) -> StoredChallenge | None: ...

    async def add_challenge(
        self, challenge: EmailChallenge, digest: bytes, source: bytes
    ) -> None: ...

    async def save_challenge(self, challenge: EmailChallenge) -> None: ...

    async def enqueue_email(self, challenge_id: UUID, sealed: bytes, at: datetime) -> None: ...

    async def cancel_email(self, challenge_id: UUID) -> None: ...

    async def bind_membership(
        self, account_id: UUID, email: StudentEmail, at: datetime
    ) -> bool: ...


class EmailUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[EmailTransaction]: ...


async def _active_actor(
    transaction: EmailTransaction, digest: bytes
) -> tuple[IdentitySnapshot, datetime]:
    identity, now = await require_session_identity(transaction, digest)
    if identity.banned:
        raise EmailActionDeniedError
    return identity, now


def _same_intent(intent: EmailIntent, fingerprint: bytes) -> None:
    if not hmac.compare_digest(intent.fingerprint, fingerprint):
        raise IdempotencyConflictError


def _created(challenge: EmailChallenge) -> ChallengeCreated:
    return ChallengeCreated(challenge.id, challenge.expires_at, challenge.resend_at)


@dataclass(frozen=True, slots=True)
class StartEmailChallenge:
    unit_of_work: EmailUnitOfWork
    hasher: SessionHasher
    vault: EmailVault
    policy: EmailPolicy = EmailPolicy()

    async def __call__(self, command: StartChallengeCommand) -> ChallengeCreated:
        digest = await self.hasher.digest(command.credential)
        fingerprint = await self.vault.fingerprint(
            ("start", command.email.value, str(command.resend_of))
        )
        async with self.unit_of_work.transaction() as transaction:
            actor, now = await _active_actor(transaction, digest)
            account_id = actor.session.account_id
            prior = await transaction.intent(account_id, EmailOperation.START, command.intent_key)
            if prior is not None:
                _same_intent(prior, fingerprint)
                stored = await transaction.lock_challenge(prior.challenge_id)
                if stored is None:
                    raise EmailChallengeUnavailableError
                return _created(stored.challenge)
            if actor.membership is not None:
                raise EmailActionDeniedError
            budget = await transaction.lock_budget(
                account_id, command.email, command.source_digest, now - timedelta(hours=1)
            )
            quota_retry = budget.retry_at(self.policy, now)
            if quota_retry is not None:
                raise EmailRateLimitedError(quota_retry)
            now = await transaction.now()
            if not actor.session.is_active(now):
                raise UnauthenticatedError
            current = await transaction.current_challenge(account_id)
            if command.resend_of is not None and (
                current is None
                or current.challenge.id != command.resend_of
                or current.challenge.session_id != actor.session.id
            ):
                raise EmailChallengeUnavailableError
            if current is not None:
                if not current.challenge.can_resend(now):
                    raise EmailRateLimitedError(current.challenge.resend_at)
                await transaction.save_challenge(current.challenge.supersede(now))
                await transaction.cancel_email(current.challenge.id)
            challenge = EmailChallenge(
                uuid4(),
                account_id,
                actor.session.id,
                command.email,
                now,
                now + self.policy.lifetime,
                now + self.policy.resend_delay,
            )
            code = await self.vault.generate_code()
            await transaction.add_challenge(
                challenge, await self.vault.code_digest(challenge.id, code), command.source_digest
            )
            await transaction.enqueue_email(
                challenge.id, await self.vault.seal_delivery(challenge.id, command.email, code), now
            )
            await transaction.remember_intent(
                account_id,
                EmailOperation.START,
                command.intent_key,
                EmailIntent(fingerprint, challenge.id, None),
            )
            return _created(challenge)


@dataclass(frozen=True, slots=True)
class VerifyStudentEmail:
    unit_of_work: EmailUnitOfWork
    hasher: SessionHasher
    vault: EmailVault

    async def __call__(self, command: VerifyChallengeCommand) -> VerificationResult:
        digest = await self.hasher.digest(command.credential)
        fingerprint = await self.vault.fingerprint(
            ("verify", str(command.challenge_id), command.code.value)
        )
        async with self.unit_of_work.transaction() as transaction:
            actor, now = await _active_actor(transaction, digest)
            account_id = actor.session.account_id
            prior = await transaction.intent(account_id, EmailOperation.VERIFY, command.intent_key)
            if prior is not None:
                _same_intent(prior, fingerprint)
                if prior.result is None:
                    raise EmailChallengeUnavailableError
                return prior.result
            stored = await transaction.lock_challenge(command.challenge_id)
            if (
                stored is None
                or stored.challenge.account_id != account_id
                or stored.challenge.session_id != actor.session.id
            ):
                raise EmailChallengeUnavailableError
            now = await transaction.now()
            if not actor.session.is_active(now):
                raise UnauthenticatedError
            challenge = stored.challenge
            matches = stored.code_digest is not None and hmac.compare_digest(
                stored.code_digest,
                await self.vault.code_digest(challenge.id, command.code),
            )
            updated, attempt = challenge.attempt(matches=matches, at=now)
            await transaction.save_challenge(updated)
            outcome = VerificationOutcome(attempt.value)
            if attempt == AttemptOutcome.VERIFIED:
                bound = actor.membership is None and await transaction.bind_membership(
                    account_id, challenge.email, now
                )
                outcome = (
                    VerificationOutcome.VERIFIED if bound else VerificationOutcome.SUPPORT_REQUIRED
                )
                await transaction.cancel_email(challenge.id)
            result = VerificationResult(
                outcome,
                MAX_CODE_ATTEMPTS - updated.attempts,
                now if outcome == VerificationOutcome.VERIFIED else None,
            )
            await transaction.remember_intent(
                account_id,
                EmailOperation.VERIFY,
                command.intent_key,
                EmailIntent(fingerprint, challenge.id, result),
            )
            if not actor.session.is_active(await transaction.now()):
                raise UnauthenticatedError
            return result


@dataclass(frozen=True, slots=True)
class ReadEmailChallenge:
    unit_of_work: EmailUnitOfWork
    hasher: SessionHasher
    policy: EmailPolicy = EmailPolicy()

    async def __call__(self, command: ReadChallengeCommand) -> ChallengeStatus:
        async with self.unit_of_work.transaction() as transaction:
            actor, now = await _active_actor(
                transaction, await self.hasher.digest(command.credential)
            )
            stored = await transaction.lock_challenge(command.challenge_id)
            if (
                stored is None
                or stored.challenge.account_id != actor.session.account_id
                or stored.challenge.session_id != actor.session.id
            ):
                raise EmailChallengeUnavailableError
            challenge = stored.challenge
            budget = await transaction.read_budget(
                actor.session.account_id,
                challenge.email,
                command.source_digest,
                now - timedelta(hours=1),
            )
            delivery = await transaction.delivery_state(challenge.id)
            outcome = await transaction.terminal_outcome(challenge.id)
            now = await transaction.now()
            quota_retry = budget.retry_at(self.policy, now)
            state = challenge.state(now)
            return ChallengeStatus(
                challenge.id,
                challenge.email,
                state,
                delivery,
                outcome,
                challenge.expires_at,
                max(challenge.resend_at, quota_retry)
                if quota_retry is not None
                else challenge.resend_at,
                MAX_CODE_ATTEMPTS - challenge.attempts,
                state == ChallengeState.ACTIVE and actor.membership is None,
                challenge.can_resend(now) and quota_retry is None and actor.membership is None,
            )
