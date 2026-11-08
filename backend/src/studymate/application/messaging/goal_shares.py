import hmac
import json
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
    SessionCredential,
    SessionHasher,
    UnauthenticatedError,
)
from studymate.application.messaging.commands import authorize_conversation
from studymate.application.messaging.ports import MessageContactUnavailableError, MessageTransaction
from studymate.application.profiles.goals import GoalVersionConflictError, SavedGoal
from studymate.domain.goal_shares import GoalShare, GoalShareState
from studymate.domain.relationships import AccountPair
from studymate.domain.requests.context import RequestContext
from studymate.domain.study_context import StudyGoal


class GoalShareContextConflictError(Exception):
    def __init__(self, current_version: int) -> None:
        super().__init__("Conversation goal context has changed")
        self.current_version = current_version


@dataclass(frozen=True, slots=True)
class ShareCurrentGoalCommand:
    credential: SessionCredential = field(repr=False)
    conversation_id: UUID
    goal_id: UUID
    expected_goal_version: int
    expected_context_version: int
    intent_key: IntentKey

    def __post_init__(self) -> None:
        if isinstance(self.expected_goal_version, bool) or self.expected_goal_version < 1:
            raise ValueError("Expected goal version must be positive")
        if isinstance(self.expected_context_version, bool) or self.expected_context_version < 0:
            raise ValueError("Expected conversation context must be nonnegative")


@dataclass(frozen=True, slots=True)
class GoalShareIntent:
    fingerprint: bytes = field(repr=False)
    result: GoalShare = field(repr=False)


class GoalShareTransaction(MessageTransaction, Protocol):
    async def active_goal(self, account_id: UUID) -> SavedGoal | None: ...

    async def goal_version(
        self, account_id: UUID, goal_id: UUID, version: int
    ) -> SavedGoal | None: ...

    async def goal_share_state(self, actor_id: UUID, conversation_id: UUID) -> GoalShareState: ...

    async def goal_share_intent(self, actor_id: UUID, key: IntentKey) -> GoalShareIntent | None: ...

    async def accepted_goal_baseline(
        self, actor_id: UUID, conversation_id: UUID
    ) -> "AcceptedGoalBaseline": ...

    async def goal_share_history(
        self, actor_id: UUID, conversation_id: UUID, window: "GoalShareWindow"
    ) -> tuple[GoalShare, ...]:
        """Owned conversation filter before source decoding, bounded descending versions."""
        ...

    async def save_goal_share(self, share: GoalShare) -> None:
        """Same locked conversation transaction: immutable row/head/canonical outcome."""
        ...

    async def remember_goal_share(
        self, actor_id: UUID, key: IntentKey, intent: GoalShareIntent, at: datetime
    ) -> None: ...


class GoalShareUnitOfWork(Protocol):
    def transaction(
        self, conversation_id: UUID
    ) -> AbstractAsyncContextManager[GoalShareTransaction]: ...


def checked_share(
    value: GoalShare, command: ShareCurrentGoalCommand, pair: AccountPair, actor_id: UUID
) -> GoalShare:
    if (
        value.conversation_id != command.conversation_id
        or value.pair != pair
        or value.owner_id != actor_id
        or value.goal.id != command.goal_id
        or value.goal.version != command.expected_goal_version
    ):
        raise RuntimeError("Goal share result differs from the actual owned source")
    return value


@dataclass(frozen=True, slots=True)
class ShareCurrentGoal:
    unit_of_work: GoalShareUnitOfWork
    hasher: SessionHasher
    fingerprinter: IntentFingerprinter

    async def __call__(self, command: ShareCurrentGoalCommand) -> GoalShare:
        async with self.unit_of_work.transaction(command.conversation_id) as transaction:
            actor, access = await authorize_conversation(
                transaction, self.hasher, command.credential, command.conversation_id
            )
            actor_id, pair = actor.session.account_id, access.conversation.pair
            digest = await self.fingerprinter.fingerprint(
                (
                    "conversation.goal.share.v1",
                    str(actor_id),
                    str(command.conversation_id),
                    str(command.goal_id),
                    str(command.expected_goal_version),
                    str(command.expected_context_version),
                )
            )
            prior = await transaction.goal_share_intent(actor_id, command.intent_key)
            if prior is not None:
                if not hmac.compare_digest(prior.fingerprint, digest):
                    raise IdempotencyConflictError
                if not actor.session.is_active(await transaction.now()):
                    raise UnauthenticatedError
                return checked_share(prior.result, command, pair, actor_id)
            if not access.can_send:
                raise MessageContactUnavailableError
            current = await transaction.active_goal(actor_id)
            if (
                current is None
                or current.goal.id != command.goal_id
                or current.goal.version != command.expected_goal_version
                or not current.goal.active
            ):
                raise GoalVersionConflictError(current)
            if current.goal.account_id != actor_id:
                raise RuntimeError("Current goal source belongs to another actor")
            state = await transaction.goal_share_state(actor_id, command.conversation_id)
            latest = state.latest
            if latest is not None and (
                latest.conversation_id != command.conversation_id or latest.pair != pair
            ):
                raise RuntimeError("Goal context belongs to another conversation")
            if (
                latest is not None
                and latest.owner_id == actor_id
                and latest.goal.id == current.goal.id
                and latest.goal.version == current.goal.version
            ):
                result = latest
            else:
                if state.context_version != command.expected_context_version:
                    raise GoalShareContextConflictError(state.context_version)
                result = GoalShare(
                    uuid4(),
                    command.conversation_id,
                    pair,
                    actor_id,
                    state.context_version + 1,
                    current.goal,
                    current.subject_label,
                    await transaction.now(),
                )
                await transaction.save_goal_share(result)
            await transaction.remember_goal_share(
                actor_id,
                command.intent_key,
                GoalShareIntent(digest, result),
                await transaction.now(),
            )
            if not actor.session.is_active(await transaction.now()):
                raise UnauthenticatedError
            return checked_share(result, command, pair, actor_id)


GOAL_SHARE_PAGE_SIZE = 50
MAX_GOAL_SHARE_CURSOR_LENGTH = 1024
MAX_CONTEXT_SEQUENCE = (1 << 63) - 1
GOAL_SHARE_CURSOR_PARTS = 5


class InvalidGoalShareCursorError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class GoalShareCursor:
    anchor_version: int
    before_version: int

    def __post_init__(self) -> None:
        if (
            any(
                isinstance(value, bool) or not 1 <= value <= MAX_CONTEXT_SEQUENCE
                for value in (self.anchor_version, self.before_version)
            )
            or self.before_version > self.anchor_version
        ):
            raise ValueError("Goal share cursor requires bounded actual context versions")


class GoalShareCursorCodec(Protocol):
    def encode(self, actor_id: UUID, conversation_id: UUID, cursor: GoalShareCursor) -> str: ...

    def decode(self, actor_id: UUID, conversation_id: UUID, token: str) -> GoalShareCursor: ...


def encode_goal_share_cursor(actor_id: UUID, conversation_id: UUID, cursor: GoalShareCursor) -> str:
    return json.dumps(
        (
            "goal-shares-v1",
            str(actor_id),
            str(conversation_id),
            str(cursor.anchor_version),
            str(cursor.before_version),
        ),
        separators=(",", ":"),
    )


def decode_goal_share_cursor(
    actor_id: UUID, conversation_id: UUID, payload: str
) -> GoalShareCursor:
    if len(payload) > MAX_GOAL_SHARE_CURSOR_LENGTH:
        raise InvalidGoalShareCursorError
    try:
        decoded: object = json.loads(payload)
        if not isinstance(decoded, list):
            raise InvalidGoalShareCursorError
        parts = tuple(value for value in decoded if isinstance(value, str))
        if len(parts) != GOAL_SHARE_CURSOR_PARTS or len(parts) != len(decoded):
            raise InvalidGoalShareCursorError
        version, actor, conversation, anchor, before = parts
        if (version, actor, conversation) != (
            "goal-shares-v1",
            str(actor_id),
            str(conversation_id),
        ):
            raise InvalidGoalShareCursorError
        cursor = GoalShareCursor(int(anchor), int(before))
        if encode_goal_share_cursor(actor_id, conversation_id, cursor) != payload:
            raise InvalidGoalShareCursorError
        return cursor
    except (ValueError, UnicodeError):
        raise InvalidGoalShareCursorError from None


@dataclass(frozen=True, slots=True)
class GoalShareWindow:
    anchor_version: int
    before_version: int | None


@dataclass(frozen=True, slots=True)
class AcceptedGoalBaseline:
    request_id: UUID
    accepted_request_version: int
    context: RequestContext = field(repr=False)


@dataclass(frozen=True, slots=True)
class GoalShareView:
    share: GoalShare = field(repr=False)
    can_complete: bool


@dataclass(frozen=True, slots=True)
class GoalBaselineView:
    baseline: AcceptedGoalBaseline = field(repr=False)
    sender_goal_can_complete: bool
    recipient_goal_can_complete: bool


@dataclass(frozen=True, slots=True)
class GoalSharePage:
    baseline: GoalBaselineView = field(repr=False)
    current_context_version: int
    latest: GoalShareView | None = field(repr=False)
    history: tuple[GoalShareView, ...] = field(repr=False)
    next_cursor: str | None
    anchor_version: int


def current_goal_matches(own: SavedGoal | None, source: StudyGoal | None) -> bool:
    return (
        own is not None
        and source is not None
        and own.goal.active
        and own.goal.account_id == source.account_id
        and own.goal.id == source.id
        and own.goal.version == source.version
    )


@dataclass(frozen=True, slots=True)
class ReadGoalShares:
    unit_of_work: GoalShareUnitOfWork
    hasher: SessionHasher
    cursor_codec: GoalShareCursorCodec

    async def __call__(
        self, credential: SessionCredential, conversation_id: UUID, cursor: str | None = None
    ) -> GoalSharePage:
        async with self.unit_of_work.transaction(conversation_id) as transaction:
            actor, access = await authorize_conversation(
                transaction, self.hasher, credential, conversation_id
            )
            actor_id, conversation = actor.session.account_id, access.conversation
            baseline = await transaction.accepted_goal_baseline(actor_id, conversation_id)
            if (
                baseline.request_id != conversation.request_id
                or baseline.accepted_request_version != conversation.accepted_request_version
                or AccountPair.between(baseline.context.sender_id, baseline.context.recipient_id)
                != conversation.pair
            ):
                raise RuntimeError("Goal baseline differs from the actual accepted request")
            state = await transaction.goal_share_state(actor_id, conversation_id)
            if state.latest is not None and (
                state.latest.conversation_id != conversation_id
                or state.latest.pair != conversation.pair
            ):
                raise RuntimeError("Current shared goal belongs to another conversation")
            position = (
                self.cursor_codec.decode(actor_id, conversation_id, cursor)
                if cursor is not None
                else None
            )
            if position is not None and position.anchor_version > state.context_version:
                raise InvalidGoalShareCursorError
            anchor = state.context_version if position is None else position.anchor_version
            window = GoalShareWindow(
                anchor, position.before_version if position is not None else None
            )
            rows = await transaction.goal_share_history(actor_id, conversation_id, window)
            if len(rows) > GOAL_SHARE_PAGE_SIZE + 1:
                raise RuntimeError("Shared goal history exceeded its bounded page")
            previous = anchor + 1
            for share in rows:
                if (
                    share.conversation_id != conversation_id
                    or share.pair != conversation.pair
                    or share.context_version >= previous
                    or (
                        window.before_version is not None
                        and share.context_version >= window.before_version
                    )
                ):
                    raise RuntimeError("Shared goal history violates owned context ordering")
                previous = share.context_version
            own = await transaction.active_goal(actor_id)
            if own is not None and own.goal.account_id != actor_id:
                raise RuntimeError("Current own goal belongs to another actor")
            visible = rows[:GOAL_SHARE_PAGE_SIZE]
            next_cursor = (
                self.cursor_codec.encode(
                    actor_id, conversation_id, GoalShareCursor(anchor, visible[-1].context_version)
                )
                if len(rows) > GOAL_SHARE_PAGE_SIZE
                else None
            )
            sender_goal, recipient_goal = (
                baseline.context.sender_goal,
                baseline.context.recipient_goal,
            )
            result = GoalSharePage(
                GoalBaselineView(
                    baseline,
                    current_goal_matches(
                        own, sender_goal.goal if sender_goal is not None else None
                    ),
                    current_goal_matches(
                        own, recipient_goal.goal if recipient_goal is not None else None
                    ),
                ),
                state.context_version,
                GoalShareView(state.latest, current_goal_matches(own, state.latest.goal))
                if state.latest is not None
                else None,
                tuple(
                    GoalShareView(share, current_goal_matches(own, share.goal))
                    for share in reversed(visible)
                ),
                next_cursor,
                anchor,
            )
            if not actor.session.is_active(await transaction.now()):
                raise UnauthenticatedError
            return result
