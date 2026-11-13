from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest

from studymate.application.errors import StorageUnavailableError
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.operator.authority import OperatorAccessDeniedError
from studymate.application.operator.cursors import InvalidOperatorCursorError, OperatorCursorScope
from studymate.application.operator.email_history import ReadOperatorEmailHistory
from studymate.application.operator.email_history_ports import EmailHistoryPosition
from studymate.infrastructure.operator.cursors import encode_cursor
from studymate.infrastructure.operator.email_history_cursors import (
    FernetOperatorEmailHistoryCursorCodec,
)
from tests.unit.identity_store import CREDENTIAL, NOW
from tests.unit.operator.email_history_store import EmailHistoryStore, challenge
from tests.unit.operator.store import TARGET
from tests.unit.operator.test_authorized_reads import HASHER

PAGE_SIZE = 50

CODEC = FernetOperatorEmailHistoryCursorCodec.from_key(b"e" * 32)


def read(store: EmailHistoryStore) -> ReadOperatorEmailHistory:
    return ReadOperatorEmailHistory(store, HASHER, CODEC)


async def test_retained_owner_scope_empty_missing_and_audit_privacy() -> None:
    store = EmailHistoryStore()
    store.assign_explicit_operator()
    store.actor = replace(
        store.actor, membership=None, registration=None, activation_complete=False
    )
    page = await read(store)(CREDENTIAL, TARGET)
    assert page is not None
    assert page.challenges == (challenge(1), challenge(2))
    assert page.as_of == NOW
    assert "retained-private" not in repr(page)
    assert "retained-private" not in repr(challenge(1))
    assert "retained-private" not in repr(store.audit)
    assert store.audit[-1].action.value == "read_account"
    store.histories[TARGET] = ()
    empty = await read(store)(CREDENTIAL, TARGET)
    assert empty is not None
    assert empty.challenges == ()
    assert empty.next_cursor is None
    assert await read(store)(CREDENTIAL, uuid4()) is None
    assert store.audit[-1].outcome.value == "not_found"


async def test_keyset_keeps_creation_boundary_but_does_not_freeze_mutable_state() -> None:
    store = EmailHistoryStore()
    store.assign_explicit_operator()
    store.histories[TARGET] = tuple(challenge(i) for i in range(1, 53))
    first = await read(store)(CREDENTIAL, TARGET)
    assert first is not None
    assert len(first.challenges) == PAGE_SIZE
    assert first.next_cursor is not None
    store.clock += timedelta(minutes=1)
    added = replace(challenge(70), created_at=store.clock)
    original = store.histories[TARGET][-1]
    store.histories[TARGET] = (
        *store.histories[TARGET][:-1],
        replace(original, consumed_at=store.clock),
        added,
    )
    second = await read(store)(CREDENTIAL, TARGET, first.next_cursor)
    assert second is not None
    assert tuple(row.id.int for row in second.challenges) == (51, 52)
    assert second.challenges[-1].consumed_at == store.clock
    assert second.as_of == first.as_of
    assert second.next_cursor is None


@pytest.mark.parametrize("state", ["absent", "revoked", "banned", "deleted", "expired"])
async def test_no_default_grant_or_lifecycle_override(state: str) -> None:
    store = EmailHistoryStore()
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
async def test_atomic_audit_and_fresh_final_authority(failure: str) -> None:
    store = EmailHistoryStore()
    store.assign_explicit_operator()
    store.fail_audit = failure == "audit"
    store.expire_after_query = failure == "expiry_query"
    store.expire_after_audit = failure == "expiry_audit"
    with pytest.raises(StorageUnavailableError if failure == "audit" else UnauthenticatedError):
        await read(store)(CREDENTIAL, TARGET)
    assert not store.audit


@pytest.mark.parametrize("fault", ["owner", "duplicate", "ascending", "future", "excess"])
async def test_bad_source_cannot_escape_owner_order_boundary_or_page_size(fault: str) -> None:
    store = EmailHistoryStore()
    store.assign_explicit_operator()
    rows = {
        "owner": (challenge(1, uuid4()),),
        "duplicate": (challenge(1), challenge(1)),
        "ascending": (challenge(2), challenge(1)),
        "future": (replace(challenge(1), created_at=NOW + timedelta(seconds=1)),),
        "excess": tuple(challenge(i) for i in range(1, 53)),
    }
    store.rows_override = rows[fault]
    with pytest.raises(RuntimeError, match="Email history"):
        await read(store)(CREDENTIAL, TARGET)
    assert not store.audit


@pytest.mark.parametrize("change", ["actor", "grant", "target", "tamper", "oversized", "future"])
def test_cursor_is_not_authority_or_cross_scope_capability(change: str) -> None:
    scope = OperatorCursorScope(uuid4(), 1)
    target = uuid4()
    position = EmailHistoryPosition(NOW, NOW - timedelta(minutes=1), uuid4())
    token = CODEC.encode_history(scope, target, position)
    assert CODEC.decode_history(scope, target, token, NOW) == position
    now = NOW
    if change == "actor":
        scope = OperatorCursorScope(uuid4(), 1)
    elif change == "grant":
        scope = OperatorCursorScope(scope.account_id, 2)
    elif change == "target":
        target = uuid4()
    elif change == "tamper":
        token = str(uuid4())
    elif change == "oversized":
        token = "x" * 1025
    else:
        now = NOW - timedelta(seconds=1)
    with pytest.raises(InvalidOperatorCursorError):
        CODEC.decode_history(scope, target, token, now)


@pytest.mark.parametrize(
    "anchor", ["not-a-time", "2026-01-01T00:00:00", "2099-01-01T00:00:00+00:00"]
)
def test_authenticated_malformed_or_naive_cursor_rejected(anchor: str) -> None:
    scope = OperatorCursorScope(uuid4(), 1)
    target = uuid4()
    token = encode_cursor(
        CODEC.cipher,
        (
            "operator-email-history-v1",
            str(scope.account_id),
            "1",
            str(target),
            anchor,
            NOW.isoformat(),
            str(uuid4()),
        ),
    )
    with pytest.raises(InvalidOperatorCursorError):
        CODEC.decode_history(scope, target, token, NOW)


def test_key_and_position_must_be_actual_aware_values() -> None:
    with pytest.raises(ValueError, match="configured32-byte"):
        FernetOperatorEmailHistoryCursorCodec.from_key(b"short")
    with pytest.raises(ValueError, match="creation boundary"):
        EmailHistoryPosition(NOW, NOW + timedelta(seconds=1), uuid4())
