from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from uuid import UUID, uuid4

import pytest

from studymate.application.changes.reads import (
    ChangeTransaction,
    InvalidChangeCursorError,
    ReadChanges,
)
from studymate.application.identity.sessions import StudentActionDeniedError, UnauthenticatedError
from studymate.domain.changes import (
    CHANGE_PAGE_SIZE,
    MAX_DELIVERY_SEQUENCE,
    ChangeHint,
    ChangeResource,
    ChangeWindow,
    PublishedChange,
)
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.unit.identity_store import CREDENTIAL, NOW, IdentityStore

OWNER = UUID(int=2)


def published(sequence: int) -> PublishedChange:
    return PublishedChange(
        ChangeHint(uuid4(), OWNER, ChangeResource.CONVERSATION, uuid4(), 1), sequence, NOW
    )


class Store(IdentityStore):
    def __init__(self) -> None:
        super().__init__()
        self.actor = replace(self.actor, activation_complete=True)
        self.window = ChangeWindow(OWNER, 0, 0, ())
        self.reads: tuple[tuple[UUID, int | None], ...] = ()
        self.expire = False

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[ChangeTransaction]:
        yield self

    async def change_window(self, recipient_id: UUID, after: int | None) -> ChangeWindow:
        self.reads += ((recipient_id, after),)
        if self.expire:
            self.clock = self.actor.session.expires_at
        return self.window


@pytest.mark.parametrize("cursor", [None, 1, MAX_DELIVERY_SEQUENCE])
async def test_initial_and_future_cursors_reset_to_actual_head_without_replaying_commands(
    cursor: int | None,
) -> None:
    store = Store()
    result = await ReadChanges(store, Sha256SessionHasher())(CREDENTIAL, cursor)
    assert result.reset_required
    assert result.after_sequence == 0
    assert not result.changes
    assert not result.has_more


async def test_caught_up_stream_does_not_invent_an_event_or_advance_beyond_handled_cursor() -> None:
    store = Store()
    result = await ReadChanges(store, Sha256SessionHasher())(CREDENTIAL, 0)
    assert not result.reset_required
    assert result.after_sequence == 0
    assert not result.changes


async def test_bounded_catchup_advances_only_through_returned_events_not_the_lookahead() -> None:
    store = Store()
    changes = tuple(published(i) for i in range(1, CHANGE_PAGE_SIZE + 2))
    store.window = ChangeWindow(OWNER, CHANGE_PAGE_SIZE + 1, 0, changes)
    result = await ReadChanges(store, Sha256SessionHasher())(CREDENTIAL, 0)
    assert result.changes == changes[:CHANGE_PAGE_SIZE]
    assert result.after_sequence == CHANGE_PAGE_SIZE
    assert result.has_more
    assert not result.reset_required
    store.window = replace(store.window, changes=changes[-1:])
    last = await ReadChanges(store, Sha256SessionHasher())(CREDENTIAL, result.after_sequence)
    assert last.changes == changes[-1:]
    assert not last.has_more
    assert last.after_sequence == CHANGE_PAGE_SIZE + 1


@pytest.mark.parametrize("cursor", [0, 1])
async def test_expired_transport_cursor_resets_without_erasing_canonical_business_history(
    cursor: int,
) -> None:
    store = Store()
    store.window = ChangeWindow(OWNER, 9, 5, ())
    result = await ReadChanges(store, Sha256SessionHasher())(CREDENTIAL, cursor)
    assert result.reset_required
    assert result.after_sequence == store.window.head_sequence
    assert not result.changes


@pytest.mark.parametrize("malformation", ["foreign", "skipped", "omitted", "truncated"])
async def test_bad_source_cannot_leak_other_actor_or_silently_skip_delivery(
    malformation: str,
) -> None:
    store = Store()
    store.window = (
        ChangeWindow(UUID(int=3), 0, 0, ())
        if malformation == "foreign"
        else ChangeWindow(OWNER, 2, 0, (published(2),))
        if malformation == "skipped"
        else ChangeWindow(OWNER, 2, 0, ())
        if malformation == "omitted"
        else ChangeWindow(OWNER, 2, 0, (published(1),))
    )
    with pytest.raises(RuntimeError):
        await ReadChanges(store, Sha256SessionHasher())(CREDENTIAL, 0)


@pytest.mark.parametrize("state", ["banned", "deleted", "unverified", "unactivated", "expired"])
async def test_stream_poll_rechecks_live_caller_authority_before_private_window(state: str) -> None:
    store = Store()
    store.actor = replace(
        store.actor,
        banned=state == "banned",
        deleted_at=NOW if state == "deleted" else None,
        membership=None if state == "unverified" else store.actor.membership,
        activation_complete=state != "unactivated",
    )
    if state == "expired":
        store.clock = store.actor.session.expires_at
    with pytest.raises((UnauthenticatedError, StudentActionDeniedError)):
        await ReadChanges(store, Sha256SessionHasher())(CREDENTIAL, 0)
    assert not store.reads


async def test_session_expiring_during_poll_returns_no_hints() -> None:
    store = Store()
    store.window = ChangeWindow(OWNER, 1, 0, (published(1),))
    store.expire = True
    with pytest.raises(UnauthenticatedError):
        await ReadChanges(store, Sha256SessionHasher())(CREDENTIAL, 0)


@pytest.mark.parametrize("cursor", [-1, True, MAX_DELIVERY_SEQUENCE + 1])
async def test_invalid_cursor_is_rejected_before_any_private_read(cursor: int) -> None:
    store = Store()
    with pytest.raises(InvalidChangeCursorError):
        await ReadChanges(store, Sha256SessionHasher())(CREDENTIAL, cursor)
    assert not store.reads


@pytest.mark.parametrize("version", [True, 0, MAX_DELIVERY_SEQUENCE + 1])
def test_hint_rejects_invalid_source_versions(version: int) -> None:
    with pytest.raises(ValueError, match="bounded source version"):
        replace(published(1).hint, version=version)


@pytest.mark.parametrize("sequence", [True, 0, MAX_DELIVERY_SEQUENCE + 1])
def test_publication_requires_an_actual_bounded_recipient_sequence(sequence: int) -> None:
    with pytest.raises(ValueError, match="positive recipient-owned"):
        replace(published(1), sequence=sequence)


@pytest.mark.parametrize(
    "malformation",
    ["negative", "bool", "floor", "foreign", "gap", "expired", "future", "unbounded"],
)
def test_window_never_accepts_foreign_missing_or_expired_delivery_positions(
    malformation: str,
) -> None:
    head, floor = 3, 0
    rows: tuple[PublishedChange, ...] = (published(1),)
    if malformation == "negative":
        head = -1
    elif malformation == "bool":
        head = True
    elif malformation == "floor":
        floor = head + 1
    elif malformation == "foreign":
        rows = (replace(rows[0], hint=replace(rows[0].hint, recipient_id=UUID(int=3))),)
    elif malformation == "gap":
        rows += (published(3),)
    elif malformation == "expired":
        floor = 1
    elif malformation == "future":
        rows = (published(head + 1),)
    elif malformation == "unbounded":
        head = CHANGE_PAGE_SIZE + 2
        rows = tuple(published(sequence) for sequence in range(1, head + 1))
    with pytest.raises(ValueError, match=r"bounded|expiry|scope"):
        ChangeWindow(OWNER, head, floor, rows)
