from dataclasses import replace
from uuid import uuid4

import pytest

from studymate.application.errors import StorageUnavailableError
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.operator.authority import OperatorAccessDeniedError
from studymate.application.operator.block_history import ReadOperatorBlockHistory
from studymate.application.operator.block_history_ports import OperatorBlockHistoryPosition
from studymate.application.operator.cursors import InvalidOperatorCursorError, OperatorCursorScope
from studymate.domain.operator.block_history import (
    OperatorBlockHistoryAnchors,
    OperatorBlockHistoryHead,
)
from studymate.domain.relationships import AccountPair
from studymate.infrastructure.operator.block_history_cursors import (
    FernetOperatorBlockHistoryCursorCodec,
)
from tests.unit.identity_store import CREDENTIAL, NOW
from tests.unit.operator.block_history_store import PAIR, RELATIONSHIP, BlockHistoryStore, revision
from tests.unit.operator.test_authorized_reads import HASHER

CODEC = FernetOperatorBlockHistoryCursorCodec.from_key(b"b" * 32)


def read(store: BlockHistoryStore) -> ReadOperatorBlockHistory:
    return ReadOperatorBlockHistory(store, HASHER, CODEC)


async def test_both_directions_are_actual_sources_under_either_account_container() -> None:
    store = BlockHistoryStore()
    store.assign_explicit_operator()
    first = await read(store)(CREDENTIAL, PAIR.low, RELATIONSHIP)
    assert first is not None
    assert first.revisions == (revision(1, PAIR.high), revision(2), revision(1))
    assert first.current_heads == (revision(1, PAIR.high), revision(2))
    assert first.anchors == OperatorBlockHistoryAnchors(2, 1)
    other = await read(store)(CREDENTIAL, PAIR.high, RELATIONSHIP)
    assert other is not None
    assert other.revisions == first.revisions
    assert store.audit[-1].requested is not None
    assert store.audit[-1].requested.id == PAIR.high
    assert store.audit[-1].results[0].id == PAIR.high
    assert store.audit[-1].action.value == "read_account"


async def test_empty_pair_has_no_synthetic_unblocked_direction_or_chat_claim() -> None:
    store = BlockHistoryStore()
    store.assign_explicit_operator()
    store.rows = ()
    result = await read(store)(CREDENTIAL, PAIR.low, RELATIONSHIP)
    assert result is not None
    assert result.current_heads == ()
    assert result.revisions == ()
    assert result.anchors == OperatorBlockHistoryAnchors(0, 0)
    assert result.next_cursor is None


async def test_missing_or_foreign_child_audits_actual_existing_container() -> None:
    store = BlockHistoryStore()
    store.assign_explicit_operator()
    other = uuid4()
    store.accounts.add(other)
    assert await read(store)(CREDENTIAL, other, RELATIONSHIP) is None
    foreign_audit = store.audit[-1]
    assert foreign_audit.outcome.value == "read"
    assert foreign_audit.results[0].id == other
    assert await read(store)(CREDENTIAL, PAIR.low, uuid4()) is None
    child_audit = store.audit[-1]
    assert child_audit.outcome.value == "read"
    assert await read(store)(CREDENTIAL, uuid4(), RELATIONSHIP) is None
    missing_audit = store.audit[-1]
    assert missing_audit.outcome.value == "not_found"
    assert missing_audit.results == ()


async def test_each_direction_is_anchored_even_when_timestamps_tie_and_both_heads_advance() -> None:
    store = BlockHistoryStore()
    store.assign_explicit_operator()
    store.rows = (
        *(revision(n) for n in range(1, 53)),
        revision(1, PAIR.high),
        revision(2, PAIR.high),
    )
    first = await read(store)(CREDENTIAL, PAIR.low, RELATIONSHIP)
    assert first is not None
    assert first.next_cursor is not None
    store.rows += (revision(53), revision(3, PAIR.high))
    second = await read(store)(CREDENTIAL, PAIR.low, RELATIONSHIP, first.next_cursor)
    assert second is not None
    assert tuple(row.version for row in second.revisions) == (4, 3, 2, 1)
    assert second.anchors == first.anchors
    assert second.current_heads == (revision(3, PAIR.high), revision(53))
    assert second.next_cursor is None


@pytest.mark.parametrize("state", ["absent", "revoked", "banned", "deleted", "expired"])
async def test_no_private_relationship_query_without_current_explicit_operator(state: str) -> None:
    store = BlockHistoryStore()
    if state != "absent":
        store.assign_explicit_operator()
    if state == "revoked":
        assert store.access is not None
        store.access = replace(store.access, active=False)
    elif state == "banned":
        store.actor = replace(store.actor, banned=True)
    elif state == "deleted":
        store.actor = replace(store.actor, deleted_at=NOW)
    elif state == "expired":
        store.clock = store.actor.session.expires_at
    error = UnauthenticatedError if state in {"deleted", "expired"} else OperatorAccessDeniedError
    with pytest.raises(error):
        await read(store)(CREDENTIAL, PAIR.low, RELATIONSHIP)
    assert store.private_queries == 0
    assert not store.audit


@pytest.mark.parametrize("failure", ["audit", "query_expiry", "audit_expiry"])
async def test_failed_audit_or_final_session_never_discloses_directional_history(
    failure: str,
) -> None:
    store = BlockHistoryStore()
    store.assign_explicit_operator()
    store.fail_audit = failure == "audit"
    store.expire_after_query = failure == "query_expiry"
    store.expire_after_audit = failure == "audit_expiry"
    with pytest.raises(StorageUnavailableError if failure == "audit" else UnauthenticatedError):
        await read(store)(CREDENTIAL, PAIR.low, RELATIONSHIP)
    assert not store.audit


@pytest.mark.parametrize(
    "change", ["actor", "grant", "container", "relationship", "pair", "tamper"]
)
def test_cursor_binds_actual_operator_container_pair_and_both_directional_anchors(
    change: str,
) -> None:
    scope, account, relation, pair = OperatorCursorScope(uuid4(), 1), PAIR.low, RELATIONSHIP, PAIR
    position = OperatorBlockHistoryPosition(OperatorBlockHistoryAnchors(2, 1), NOW, PAIR.low, 1)
    token = CODEC.encode_history(scope, account, relation, pair, position)
    assert CODEC.decode_history(scope, account, relation, pair, token) == position
    if change == "actor":
        scope = OperatorCursorScope(uuid4(), 1)
    elif change == "grant":
        scope = OperatorCursorScope(scope.account_id, 2)
    elif change == "container":
        account = PAIR.high
    elif change == "relationship":
        relation = uuid4()
    elif change == "pair":
        pair = AccountPair.between(PAIR.low, uuid4())
    else:
        token = str(uuid4())
    with pytest.raises(InvalidOperatorCursorError):
        CODEC.decode_history(scope, account, relation, pair, token)


@pytest.mark.parametrize(
    "fault", ["pair", "relation", "duplicate", "ascending", "above_anchor", "excess"]
)
async def test_retained_source_scope_order_and_anchor_are_not_trusted_blindly(fault: str) -> None:
    store = BlockHistoryStore()
    store.assign_explicit_operator()
    otherpair = AccountPair.between(PAIR.low, uuid4())
    store.rows_override = {
        "pair": (replace(revision(1), pair=otherpair),),
        "relation": (replace(revision(1), relationship_id=uuid4()),),
        "duplicate": (revision(1), revision(1)),
        "ascending": (revision(1), revision(2)),
        "above_anchor": (revision(3),),
        "excess": tuple(revision(1) for _ in range(52)),
    }[fault]
    with pytest.raises(RuntimeError, match="Block history"):
        await read(store)(CREDENTIAL, PAIR.low, RELATIONSHIP)
    assert not store.audit


async def test_future_directional_anchor_and_foreign_pair_head_do_not_grant_data() -> None:
    store = BlockHistoryStore()
    store.assign_explicit_operator()
    scope = OperatorCursorScope(store.actor.session.account_id, 1)
    token = CODEC.encode_history(
        scope,
        PAIR.low,
        RELATIONSHIP,
        PAIR,
        OperatorBlockHistoryPosition(OperatorBlockHistoryAnchors(3, 1), NOW, PAIR.low, 1),
    )
    with pytest.raises(InvalidOperatorCursorError):
        await read(store)(CREDENTIAL, PAIR.low, RELATIONSHIP, token)
    foreignpair = AccountPair.between(uuid4(), uuid4())
    store.head_override = OperatorBlockHistoryHead(
        RELATIONSHIP, foreignpair, OperatorBlockHistoryAnchors(0, 0), ()
    )
    with pytest.raises(RuntimeError, match="pair source"):
        await read(store)(CREDENTIAL, PAIR.low, RELATIONSHIP)
    assert not store.audit
