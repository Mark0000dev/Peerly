"""Read transport hints in short authenticated transactions, never across network waits."""

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from studymate.application.identity.sessions import (
    IdentityReader,
    SessionCredential,
    SessionHasher,
    StudentActionDeniedError,
    UnauthenticatedError,
    require_verified_student,
)
from studymate.domain.changes import (
    CHANGE_PAGE_SIZE,
    MAX_DELIVERY_SEQUENCE,
    ChangeWindow,
    PublishedChange,
)


class InvalidChangeCursorError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class ChangePage:
    changes: tuple[PublishedChange, ...]
    after_sequence: int
    reset_required: bool
    has_more: bool


class ChangeTransaction(IdentityReader, Protocol):
    async def change_window(self, recipient_id: UUID, after: int | None) -> ChangeWindow:
        """Read published recipient head/retention floor and at most51 contiguous hints."""
        ...


class ChangeUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[ChangeTransaction]: ...


@dataclass(frozen=True, slots=True)
class ReadChanges:
    unit_of_work: ChangeUnitOfWork
    hasher: SessionHasher

    async def __call__(self, credential: SessionCredential, after: int | None) -> ChangePage:
        if after is not None and (
            isinstance(after, bool) or not 0 <= after <= MAX_DELIVERY_SEQUENCE
        ):
            raise InvalidChangeCursorError
        async with self.unit_of_work.transaction() as transaction:
            actor, _ = await require_verified_student(
                transaction, await self.hasher.digest(credential)
            )
            if not actor.activation_complete:
                raise StudentActionDeniedError
            recipient = actor.session.account_id
            window = await transaction.change_window(recipient, after)
            if window.recipient_id != recipient:
                raise RuntimeError("Change projection belongs to another authenticated recipient")
            if (
                after is None
                or not window.expired_through_sequence <= after <= window.head_sequence
            ):
                result = ChangePage((), window.head_sequence, True, False)
            else:
                if window.changes:
                    if window.changes[0].sequence != after + 1:
                        raise RuntimeError("Change stream would skip an unhandled retained event")
                elif after != window.head_sequence:
                    raise RuntimeError("Change projection omitted retained published events")
                if (
                    window.changes
                    and len(window.changes) <= CHANGE_PAGE_SIZE
                    and window.changes[-1].sequence != window.head_sequence
                ):
                    raise RuntimeError(
                        "Change projection truncated before its declared stream head"
                    )
                page = window.changes[:CHANGE_PAGE_SIZE]
                result = ChangePage(
                    page,
                    page[-1].sequence if page else after,
                    False,
                    len(window.changes) > CHANGE_PAGE_SIZE,
                )
            if not actor.session.is_active(await transaction.now()):
                raise UnauthenticatedError
            return result
