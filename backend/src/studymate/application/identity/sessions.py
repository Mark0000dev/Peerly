"""Session-owned identity reads and revocation, independent of Google transport."""

import re
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID

from studymate.domain.identity import Session
from studymate.domain.membership import Membership
from studymate.domain.registration import RegistrationReceipt

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}")


class UnauthenticatedError(Exception):
    """Missing, invalid, expired or revoked credentials; never disclose details."""


class StudentActionDeniedError(Exception):
    """Authenticated account does not satisfy the student capability gate."""


@dataclass(frozen=True, slots=True)
class SessionCredential:
    value: str = field(repr=False)

    def __post_init__(self) -> None:
        if not _TOKEN_PATTERN.fullmatch(self.value):
            raise UnauthenticatedError


@dataclass(frozen=True, slots=True)
class IdentitySnapshot:
    session: Session
    membership: Membership | None
    banned: bool
    deleted_at: datetime | None = None
    registration: RegistrationReceipt | None = None
    email_challenge_id: UUID | None = None
    activation_complete: bool = False


class SessionHasher(Protocol):
    async def digest(self, credential: SessionCredential) -> bytes: ...


class IdentityReader(Protocol):
    def authenticated(self, account_id: UUID) -> None:
        """Attach only the actor proven by this use case; no SDK or extra I/O."""
        ...

    async def lock_identity(self, secret_digest: bytes) -> IdentitySnapshot | None: ...

    async def now(self) -> datetime: ...


class IdentityTransaction(IdentityReader, Protocol):
    async def revoke_session(self, session_id: UUID, at: datetime) -> None: ...


class IdentityUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[IdentityTransaction]: ...


async def require_session_identity(
    transaction: IdentityReader,
    digest: bytes,
) -> tuple[IdentitySnapshot, datetime]:
    """A ban stays authenticated for limited routes; deletion never does."""
    identity = await transaction.lock_identity(digest)
    now = await transaction.now()
    if identity is None or identity.deleted_at is not None or not identity.session.is_active(now):
        raise UnauthenticatedError
    transaction.authenticated(identity.session.account_id)
    return identity, now


async def require_verified_student(
    transaction: IdentityReader, digest: bytes
) -> tuple[IdentitySnapshot, datetime]:
    identity, now = await require_session_identity(transaction, digest)
    if identity.banned or identity.membership is None or not identity.membership.is_verified:
        raise StudentActionDeniedError
    return identity, now


@dataclass(frozen=True, slots=True)
class ReadIdentity:
    unit_of_work: IdentityUnitOfWork
    hasher: SessionHasher

    async def __call__(self, credential: SessionCredential) -> IdentitySnapshot:
        digest = await self.hasher.digest(credential)
        async with self.unit_of_work.transaction() as transaction:
            identity, _ = await require_session_identity(transaction, digest)
            return identity


@dataclass(frozen=True, slots=True)
class Logout:
    unit_of_work: IdentityUnitOfWork
    hasher: SessionHasher

    async def __call__(self, credential: SessionCredential) -> None:
        digest = await self.hasher.digest(credential)
        async with self.unit_of_work.transaction() as transaction:
            identity = await transaction.lock_identity(digest)
            if identity is not None and identity.session.revoked_at is None:
                now = await transaction.now()
                if identity.deleted_at is None and identity.session.is_active(now):
                    transaction.authenticated(identity.session.account_id)
                await transaction.revoke_session(identity.session.id, now)
