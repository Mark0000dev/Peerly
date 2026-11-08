import base64
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from uuid import UUID, uuid4

import pytest

from studymate.application.identity.sessions import StudentActionDeniedError, UnauthenticatedError
from studymate.application.safety.block_list import (
    BLOCKS_PAGE_SIZE,
    BlockCursor,
    InvalidBlockCursorError,
    OwnBlockedPerson,
    OwnBlocksReader,
    ReadOwnBlocks,
    decode_block_cursor,
    encode_block_cursor,
)
from studymate.application.safety.blocks import OwnBlockResult
from studymate.domain.profiles import DisplayName
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.unit.identity_store import CREDENTIAL, NOW, IdentityStore


class Store(IdentityStore):
    def __init__(self) -> None:
        super().__init__()
        self.actor = replace(self.actor, activation_complete=True)
        self.people: tuple[OwnBlockedPerson, ...] = ()
        self.expire_when_read = False

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[OwnBlocksReader]:
        yield self

    async def blocked_people(
        self, actor_id: UUID, after: BlockCursor | None, limit: int
    ) -> tuple[OwnBlockedPerson, ...]:
        assert actor_id == self.actor.session.account_id
        assert limit == BLOCKS_PAGE_SIZE + 1
        assert after is None or after.changed_at <= NOW
        if self.expire_when_read:
            self.clock = self.actor.session.expires_at
        return self.people


def person(actor_id: UUID, *, deleted: bool = False) -> OwnBlockedPerson:
    return OwnBlockedPerson(
        actor_id, OwnBlockResult(uuid4(), True, 1, NOW), DisplayName("Known original name"), deleted
    )


async def test_own_block_page_is_bounded_and_cursor_is_actor_bound() -> None:
    store = Store()
    actor_id = store.actor.session.account_id
    store.people = tuple(person(actor_id) for _ in range(BLOCKS_PAGE_SIZE + 1))
    page = await ReadOwnBlocks(store, Sha256SessionHasher())(CREDENTIAL)
    assert len(page.people) == BLOCKS_PAGE_SIZE
    assert page.next_cursor is not None
    decoded = decode_block_cursor(actor_id, page.next_cursor)
    assert decoded.changed_at == NOW
    assert decoded.target_id == page.people[-1].block.target_id
    with pytest.raises(InvalidBlockCursorError):
        decode_block_cursor(uuid4(), page.next_cursor)


async def test_deleted_person_name_is_masked_without_mutating_retained_source() -> None:
    store = Store()
    store.people = (person(store.actor.session.account_id, deleted=True),)
    result = await ReadOwnBlocks(store, Sha256SessionHasher())(CREDENTIAL)
    assert result.people[0].deleted
    assert result.people[0].display_name is None
    assert store.people[0].display_name == DisplayName("Known original name")
    assert result.next_cursor is None


@pytest.mark.parametrize("state", ["unverified", "banned", "deleted", "not_activated", "expired"])
async def test_own_blocks_requires_live_verified_activated_actor(state: str) -> None:
    store = Store()
    store.actor = replace(
        store.actor,
        membership=None if state == "unverified" else store.actor.membership,
        banned=state == "banned",
        deleted_at=NOW if state == "deleted" else None,
        activation_complete=state != "not_activated",
    )
    if state == "expired":
        store.expire_when_read = True
    expected = UnauthenticatedError if state in {"deleted", "expired"} else StudentActionDeniedError
    with pytest.raises(expected):
        await ReadOwnBlocks(store, Sha256SessionHasher())(CREDENTIAL)


async def test_foreign_block_projection_is_never_returned() -> None:
    store = Store()
    store.people = (person(uuid4()),)
    with pytest.raises(RuntimeError, match="scope"):
        await ReadOwnBlocks(store, Sha256SessionHasher())(CREDENTIAL)


@pytest.mark.parametrize("encoded", ["!", "a" * 513, "abcd", "W10", "bnVsbA", "e30"])
def test_invalid_block_cursor_never_reaches_persistence(encoded: str) -> None:
    with pytest.raises(InvalidBlockCursorError):
        decode_block_cursor(UUID(int=2), encoded)


def test_cursor_is_canonical_and_timezone_aware() -> None:
    actor_id, target_id = UUID(int=2), uuid4()
    cursor = BlockCursor(NOW, target_id)
    encoded = encode_block_cursor(actor_id, cursor)
    assert decode_block_cursor(actor_id, encoded) == cursor
    with pytest.raises(InvalidBlockCursorError):
        decode_block_cursor(actor_id, encoded + "=")
    naive = (
        base64.urlsafe_b64encode(
            json.dumps(
                ["blocks-v1", str(actor_id), "2026-11-07T00:00:00", str(target_id)],
                separators=(",", ":"),
            ).encode()
        )
        .decode()
        .rstrip("=")
    )
    with pytest.raises(InvalidBlockCursorError):
        decode_block_cursor(actor_id, naive)
