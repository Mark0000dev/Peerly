"""Owner-only active block management; historical names never track hidden edits."""

import base64
import binascii
import json
import re
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
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
from studymate.application.safety.blocks import OwnBlockResult
from studymate.domain.profiles import DisplayName
from studymate.domain.time import require_aware

BLOCKS_PAGE_SIZE = 20
CURSOR_PARTS = 4


class InvalidBlockCursorError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class BlockCursor:
    changed_at: datetime
    target_id: UUID

    def __post_init__(self) -> None:
        require_aware(self.changed_at)


def encode_block_cursor(actor_id: UUID, cursor: BlockCursor) -> str:
    payload = json.dumps(
        (
            "blocks-v1",
            str(actor_id),
            cursor.changed_at.astimezone(UTC).isoformat(),
            str(cursor.target_id),
        ),
        separators=(",", ":"),
    ).encode("ascii")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def decode_block_cursor(actor_id: UUID, encoded: str) -> BlockCursor:
    if re.fullmatch(r"[A-Za-z0-9_-]{1,512}", encoded) is None:
        raise InvalidBlockCursorError
    try:
        payload: object = json.loads(
            base64.b64decode(encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True)
        )
        if not isinstance(payload, list):
            raise InvalidBlockCursorError
        strings = tuple(value for value in payload if isinstance(value, str))
        if len(strings) != CURSOR_PARTS or len(strings) != len(payload):
            raise InvalidBlockCursorError
        version, account, timestamp, target = strings
        if version != "blocks-v1" or UUID(account) != actor_id:
            raise InvalidBlockCursorError
        cursor = BlockCursor(datetime.fromisoformat(timestamp), UUID(target))
        if encode_block_cursor(actor_id, cursor) != encoded:
            raise InvalidBlockCursorError
        return cursor
    except (ValueError, UnicodeError, binascii.Error):
        raise InvalidBlockCursorError from None


@dataclass(frozen=True, slots=True)
class OwnBlockedPerson:
    actor_id: UUID
    block: OwnBlockResult
    display_name: DisplayName | None = field(repr=False)
    deleted: bool

    def __post_init__(self) -> None:
        if (
            not self.block.blocked
            or self.block.version < 1
            or self.block.target_id == self.actor_id
        ):
            raise ValueError("Block management entries must represent an actual own active block")


@dataclass(frozen=True, slots=True)
class OwnBlocksPage:
    people: tuple[OwnBlockedPerson, ...] = field(repr=False)
    next_cursor: str | None


class OwnBlocksReader(IdentityReader, Protocol):
    async def blocked_people(
        self, actor_id: UUID, after: BlockCursor | None, limit: int
    ) -> tuple[OwnBlockedPerson, ...]: ...


class OwnBlocksUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[OwnBlocksReader]: ...


@dataclass(frozen=True, slots=True)
class ReadOwnBlocks:
    unit_of_work: OwnBlocksUnitOfWork
    hasher: SessionHasher

    async def __call__(
        self, credential: SessionCredential, cursor: str | None = None
    ) -> OwnBlocksPage:
        async with self.unit_of_work.transaction() as transaction:
            actor, _ = await require_verified_student(
                transaction, await self.hasher.digest(credential)
            )
            if not actor.activation_complete:
                raise StudentActionDeniedError
            actor_id = actor.session.account_id
            after = decode_block_cursor(actor_id, cursor) if cursor is not None else None
            records = await transaction.blocked_people(actor_id, after, BLOCKS_PAGE_SIZE + 1)
            if len(records) > BLOCKS_PAGE_SIZE + 1 or any(
                row.actor_id != actor_id for row in records
            ):
                raise RuntimeError("Own block page exceeds its authorised projection scope")
            people = tuple(
                replace(row, display_name=None) if row.deleted else row
                for row in records[:BLOCKS_PAGE_SIZE]
            )
            next_cursor = None
            if len(records) > BLOCKS_PAGE_SIZE:
                last = people[-1].block
                if last.changed_at is None:
                    raise RuntimeError("Active block cannot lack its saved revision time")
                next_cursor = encode_block_cursor(
                    actor_id, BlockCursor(last.changed_at, last.target_id)
                )
            if not actor.session.is_active(await transaction.now()):
                raise UnauthenticatedError
            return OwnBlocksPage(people, next_cursor)
