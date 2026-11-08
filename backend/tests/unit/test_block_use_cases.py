from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime
from uuid import UUID, uuid4

import pytest

from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.safety.blocks import (
    BlockIntent,
    BlockTargetUnavailableError,
    BlockTransaction,
    BlockVersionConflictError,
    ChangeBlockCommand,
    ChangeOwnBlock,
    OwnBlockResult,
    OwnBlockSnapshot,
)
from studymate.domain.relationships import AccountPair, BlockRevision, pair_is_blocked
from studymate.domain.reports import ProfileAccessContext, ProfileVersionRefs
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.unit.identity_store import CREDENTIAL, IdentityStore

TARGET = UUID(int=99)
CONTEXT = UUID(int=3)


class Store(IdentityStore):
    def __init__(self, *, expire_before_commit: bool = False) -> None:
        super().__init__()
        self.actor = replace(self.actor, activation_complete=True)
        self.contexts = {
            CONTEXT: ProfileAccessContext(
                CONTEXT,
                self.actor.session.account_id,
                ProfileVersionRefs(TARGET, 1, 1, None, None, None),
                self.clock,
            )
        }
        self.pairs: dict[AccountPair, UUID] = {}
        self.blocks: dict[tuple[UUID, UUID], BlockRevision] = {}
        self.intents: dict[str, BlockIntent] = {}
        self.expire_before_commit = expire_before_commit

    @asynccontextmanager
    async def transaction(self, _target_id: UUID) -> AsyncIterator[BlockTransaction]:
        pairs, blocks, intents = self.pairs.copy(), self.blocks.copy(), self.intents.copy()
        try:
            yield self
        except BaseException:
            self.pairs, self.blocks, self.intents = pairs, blocks, intents
            raise

    async def block_intent(self, actor_id: UUID, key: IntentKey) -> BlockIntent | None:
        assert actor_id == self.actor.session.account_id
        return self.intents.get(key.value)

    async def current_own_block(self, actor_id: UUID, target_id: UUID) -> OwnBlockSnapshot:
        pair = AccountPair.between(actor_id, target_id)
        return OwnBlockSnapshot(pair, self.pairs.get(pair), self.blocks.get((actor_id, target_id)))

    async def access_context(self, actor_id: UUID, context_id: UUID) -> ProfileAccessContext | None:
        assert actor_id == self.actor.session.account_id
        return self.contexts.get(context_id)

    async def save_block(self, revision: BlockRevision) -> None:
        assert (
            self.pairs.setdefault(revision.pair, revision.relationship_id)
            == revision.relationship_id
        )
        self.blocks[(revision.blocker_id, revision.target_id)] = revision

    async def remember_block_intent(
        self, actor_id: UUID, key: IntentKey, intent: BlockIntent, at: datetime
    ) -> None:
        assert actor_id == self.actor.session.account_id
        assert at == self.clock
        self.intents[key.value] = intent
        if self.expire_before_commit:
            self.clock = self.actor.session.expires_at


def service(store: Store) -> ChangeOwnBlock:
    return ChangeOwnBlock(store, Sha256SessionHasher(), HmacIntentFingerprinter(bytes(range(32))))


def command() -> ChangeBlockCommand:
    return ChangeBlockCommand(CREDENTIAL, TARGET, True, 0, IntentKey("synthetic-intent"), CONTEXT)


async def test_block_replays_original_result_and_rejects_stale_edits() -> None:
    store = Store()
    change = service(store)
    first = await change(command())
    assert first.blocked
    assert first.version == 1
    assert await change(command()) == first
    same = await change(
        replace(command(), expected_version=first.version, intent_key=IntentKey(str(uuid4())))
    )
    assert same == first
    assert len(store.blocks) == 1
    with pytest.raises(IdempotencyConflictError):
        await change(replace(command(), blocked=False))
    with pytest.raises(BlockVersionConflictError):
        await change(replace(command(), intent_key=IntentKey(str(uuid4()))))
    unblocked = await change(
        replace(
            command(),
            blocked=False,
            expected_version=first.version,
            intent_key=IntentKey(str(uuid4())),
            context_id=None,
        )
    )
    assert not unblocked.blocked
    assert unblocked.version == first.version + 1
    assert await change(command()) == first
    assert not store.blocks[(store.actor.session.account_id, TARGET)].blocked


async def test_absent_unblock_does_not_invent_a_pair_block_or_history_revision() -> None:
    store = Store()
    result = await service(store)(replace(command(), blocked=False))
    assert result == OwnBlockResult(TARGET, False, 0, None)
    assert store.pairs == {}
    assert store.blocks == {}
    assert len(store.intents) == 1


async def test_unblock_controls_only_own_direction_even_when_counterpart_also_blocked() -> None:
    store = Store()
    change = service(store)
    first = await change(command())
    actor_id = store.actor.session.account_id
    own = store.blocks[(actor_id, TARGET)]
    other = replace(own, blocker_id=TARGET)
    store.blocks[(TARGET, actor_id)] = other
    result = await change(
        replace(
            command(),
            blocked=False,
            expected_version=first.version,
            intent_key=IntentKey(str(uuid4())),
            context_id=None,
        )
    )
    assert not result.blocked
    assert store.blocks[(TARGET, actor_id)] is other
    assert pair_is_blocked(store.blocks[(actor_id, TARGET)], other)


@pytest.mark.parametrize("reason", ["missing", "foreign", "other_target", "self"])
async def test_unknown_target_never_gains_access_from_a_guessed_or_foreign_context(
    reason: str,
) -> None:
    store = Store()
    submitted = command()
    context = store.contexts[CONTEXT]
    if reason == "missing":
        submitted = replace(submitted, context_id=None)
    elif reason == "foreign":
        store.contexts[CONTEXT] = replace(context, viewer_id=UUID(int=100))
    elif reason == "other_target":
        submitted = replace(submitted, target_id=UUID(int=100))
    else:
        submitted = replace(submitted, target_id=store.actor.session.account_id)
    with pytest.raises(BlockTargetUnavailableError):
        await service(store)(submitted)
    assert store.blocks == {}
    assert store.intents == {}


async def test_block_expiry_before_commit_rolls_back_pair_and_saved_retry_result() -> None:
    store = Store(expire_before_commit=True)
    with pytest.raises(UnauthenticatedError):
        await service(store)(command())
    assert store.blocks == {}
    assert store.pairs == {}
    assert store.intents == {}


async def test_corrupt_original_result_is_not_returned_for_another_target() -> None:
    store = Store()
    change = service(store)
    await change(command())
    intent = store.intents[command().intent_key.value]
    store.intents[command().intent_key.value] = replace(
        intent, result=replace(intent.result, target_id=UUID(int=100))
    )
    with pytest.raises(RuntimeError, match="another target"):
        await change(command())


@pytest.mark.parametrize("version", [-1, True])
def test_expected_block_version_rejects_negative_and_boolean_values(version: int) -> None:
    with pytest.raises(ValueError, match="nonnegative"):
        replace(command(), expected_version=version)
