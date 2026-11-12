from dataclasses import replace
from uuid import uuid4

import pytest

from studymate.application.errors import StorageUnavailableError
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.operator.access_history import ReadOperatorAccessHistory
from studymate.application.operator.access_history_ports import (
    OperatorAccessHistoryHead,
    OperatorAccessHistoryPosition,
)
from studymate.application.operator.authority import OperatorAccessDeniedError
from studymate.application.operator.cursors import InvalidOperatorCursorError, OperatorCursorScope
from studymate.domain.operator.access_history import OPERATOR_ACCESS_HISTORY_PAGE_SIZE
from studymate.domain.operator.audit import (
    OperatorAction,
    OperatorAuditOutcome,
    OperatorResourceKind,
    OperatorResourceRef,
)
from studymate.infrastructure.operator.access_history_cursors import (
    FernetOperatorAccessHistoryCursorCodec,
)
from studymate.infrastructure.operator.cursors import encode_cursor
from tests.unit.identity_store import CREDENTIAL, NOW
from tests.unit.operator.access_history_store import HistoryStore, revision
from tests.unit.operator.store import TARGET
from tests.unit.operator.test_authorized_reads import HASHER

CODEC = FernetOperatorAccessHistoryCursorCodec.from_key(b"h" * 32)


def read(store: HistoryStore) -> ReadOperatorAccessHistory:
    return ReadOperatorAccessHistory(store, HASHER, CODEC)


async def test_raw_history_preserves_real_account_scope_and_clock_regression() -> None:
    store = HistoryStore()
    store.assign_explicit_operator()
    store.actor = replace(
        store.actor, membership=None, activation_complete=False, registration=None
    )
    result = await read(store)(CREDENTIAL, TARGET)
    assert result is not None
    assert tuple(row.version for row in result.revisions) == (3, 2, 1)
    assert result.revisions[0].changed_at < result.revisions[-1].changed_at
    assert result.revisions[0].changed_by_id == revision(3).changed_by_id
    assert result.revisions[-1].changed_by_id is None
    assert result.revisions[0].active
    audit = store.audit[-1]
    resource = OperatorResourceRef(OperatorResourceKind.ACCOUNT, TARGET)
    assert audit.action == OperatorAction.READ_ACCOUNT
    assert audit.requested == resource
    assert audit.results == (resource,)
    assert audit.outcome == OperatorAuditOutcome.READ


async def test_existing_empty_account_reads_but_missing_account_commits_not_found() -> None:
    store = HistoryStore()
    store.assign_explicit_operator()
    store.histories[TARGET] = ()
    result = await read(store)(CREDENTIAL, TARGET)
    assert result is not None
    assert result.revisions == ()
    assert result.anchor_version == 0
    assert result.next_cursor is None
    original_read = store.audit[-1]
    assert original_read.results == (OperatorResourceRef(OperatorResourceKind.ACCOUNT, TARGET),)
    assert await read(store)(CREDENTIAL, uuid4()) is None
    assert store.audit[-1].outcome == OperatorAuditOutcome.NOT_FOUND
    assert store.audit[-1].results == ()


async def test_version_pagination_excludes_new_higher_revision_from_old_page() -> None:
    store = HistoryStore()
    store.assign_explicit_operator()
    last_version = OPERATOR_ACCESS_HISTORY_PAGE_SIZE + 2
    store.histories[TARGET] = tuple(revision(number) for number in range(1, last_version + 1))
    first = await read(store)(CREDENTIAL, TARGET)
    assert first is not None
    assert len(first.revisions) == OPERATOR_ACCESS_HISTORY_PAGE_SIZE
    assert first.next_cursor is not None
    store.histories[TARGET] += (revision(last_version + 1),)
    second = await read(store)(CREDENTIAL, TARGET, first.next_cursor)
    assert second is not None
    assert tuple(row.version for row in second.revisions) == (2, 1)
    assert second.anchor_version == first.anchor_version
    assert second.next_cursor is None
    refreshed = await read(store)(CREDENTIAL, TARGET)
    assert refreshed is not None
    assert refreshed.anchor_version == last_version + 1


@pytest.mark.parametrize("state", ["absent", "revoked", "banned", "deleted", "expired"])
async def test_no_implicit_operator_or_lifecycle_override(state: str) -> None:
    store = HistoryStore()
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
        await read(store)(CREDENTIAL, TARGET)
    assert store.private_queries == 0
    assert not store.audit


@pytest.mark.parametrize("failure", ["audit", "expiry_query", "expiry_audit"])
async def test_failed_audit_or_final_session_never_returns_private_history(failure: str) -> None:
    store = HistoryStore()
    store.assign_explicit_operator()
    store.fail_audit = failure == "audit"
    store.expire_after_query = failure == "expiry_query"
    store.expire_after_audit = failure == "expiry_audit"
    with pytest.raises(StorageUnavailableError if failure == "audit" else UnauthenticatedError):
        await read(store)(CREDENTIAL, TARGET)
    assert not store.audit


@pytest.mark.parametrize("fault", ["owner", "duplicate", "ascending", "above_anchor", "excess"])
async def test_source_must_match_actual_target_and_bounded_descending_versions(fault: str) -> None:
    store = HistoryStore()
    store.assign_explicit_operator()
    rows = {
        "owner": (revision(1, uuid4()),),
        "duplicate": (revision(2), revision(2)),
        "ascending": (revision(1), revision(2)),
        "above_anchor": (revision(4),),
        "excess": tuple(revision(1) for _ in range(OPERATOR_ACCESS_HISTORY_PAGE_SIZE + 2)),
    }
    store.rows_override = rows[fault]
    with pytest.raises(RuntimeError, match="Operator-access history"):
        await read(store)(CREDENTIAL, TARGET)
    assert not store.audit


async def test_cross_account_head_and_future_cursor_are_never_source_authority() -> None:
    store = HistoryStore()
    store.assign_explicit_operator()
    store.head_override = OperatorAccessHistoryHead(uuid4(), 3)
    with pytest.raises(RuntimeError, match="another actual account"):
        await read(store)(CREDENTIAL, TARGET)
    store.head_override = None
    scope = OperatorCursorScope(store.actor.session.account_id, 1)
    token = CODEC.encode_history(scope, TARGET, OperatorAccessHistoryPosition(4, 2))
    with pytest.raises(InvalidOperatorCursorError):
        await read(store)(CREDENTIAL, TARGET, token)
    assert not store.audit


@pytest.mark.parametrize("scope_change", ["actor", "grant", "target", "tampered", "oversized"])
def test_opaque_cursor_is_bound_to_actual_actor_role_target_and_version(scope_change: str) -> None:
    scope = OperatorCursorScope(uuid4(), 1)
    target = uuid4()
    position = OperatorAccessHistoryPosition(5, 2)
    token = CODEC.encode_history(scope, target, position)
    assert CODEC.decode_history(scope, target, token) == position
    if scope_change == "actor":
        scope = OperatorCursorScope(uuid4(), 1)
    elif scope_change == "grant":
        scope = OperatorCursorScope(scope.account_id, 2)
    elif scope_change == "target":
        target = uuid4()
    elif scope_change == "tampered":
        token = str(uuid4())
    else:
        token = "x" * 1025
    with pytest.raises(InvalidOperatorCursorError):
        CODEC.decode_history(scope, target, token)


@pytest.mark.parametrize(
    ("anchor", "before"),
    [("0", "1"), ("1", "2"), ("+2", "1"), ("2", "+1"), ("false", "1"), ("2147483648", "1")],
)
def test_authenticated_but_invalid_version_cursor_is_rejected(anchor: str, before: str) -> None:
    scope = OperatorCursorScope(uuid4(), 1)
    target = uuid4()
    token = encode_cursor(
        CODEC.cipher,
        (
            "operator-access-history-v1",
            str(scope.account_id),
            "1",
            str(target),
            anchor,
            before,
        ),
    )
    with pytest.raises(InvalidOperatorCursorError):
        CODEC.decode_history(scope, target, token)


def test_legacy_nulls_and_bounded_versions_are_not_fabricated() -> None:
    original = revision(1)
    assert original.changed_by_id is None
    assert original.http_request_id is None
    assert original.trace_id is None
    assert original.span_id is None
    with pytest.raises(ValueError, match="bounded nonnegative"):
        OperatorAccessHistoryHead(TARGET, -1)
    with pytest.raises(ValueError, match="bounded source versions"):
        OperatorAccessHistoryPosition(2, 3)
    with pytest.raises(ValueError, match="bounded positive"):
        replace(original, version=0)
    with pytest.raises(ValueError, match="32-byte"):
        FernetOperatorAccessHistoryCursorCodec.from_key(b"short")
