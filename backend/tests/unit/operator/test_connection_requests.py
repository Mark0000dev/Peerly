from dataclasses import replace
from datetime import timedelta
from uuid import UUID, uuid4

import pytest

from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.operator.authority import OperatorAccessDeniedError
from studymate.application.operator.connection_requests import (
    ReadOperatorRequestHistory,
    ReadOperatorRequests,
)
from studymate.application.operator.cursors import InvalidOperatorCursorError, OperatorCursorScope
from studymate.application.operator.request_ports import (
    OperatorRequestDirection,
    OperatorRequestFilters,
    OperatorRequestHistoryHead,
    OperatorRequestHistoryPosition,
    OperatorRequestPosition,
)
from studymate.domain.discovery import DiscoveryMode
from studymate.domain.operator.audit import OperatorAuditOutcome
from studymate.domain.operator.connection_requests import (
    OPERATOR_REQUEST_PAGE_SIZE,
    OPERATOR_REQUEST_SOURCE_BYTES,
)
from studymate.domain.requests.states import RequestState
from studymate.infrastructure.operator.cursors import encode_cursor
from studymate.infrastructure.operator.request_cursors import FernetOperatorRequestCursorCodec
from tests.unit.identity_store import CREDENTIAL, NOW
from tests.unit.operator.request_store import (
    PEER,
    RAW_NOTE,
    RAW_SOURCE,
    RAW_TEXT,
    REQUEST,
    RequestStore,
    ack,
    revision,
    root,
    snapshot,
)
from tests.unit.operator.store import TARGET
from tests.unit.operator.test_authorized_reads import FINGERPRINTER, HASHER

CODEC = FernetOperatorRequestCursorCodec.from_key(b"r" * 32)


def requests(store: RequestStore) -> ReadOperatorRequests:
    return ReadOperatorRequests(store, HASHER, FINGERPRINTER, CODEC)


def history(store: RequestStore) -> ReadOperatorRequestHistory:
    return ReadOperatorRequestHistory(store, HASHER, CODEC)


async def test_both_participant_scopes_preserve_raw_source_without_settlement() -> None:
    store = RequestStore()
    store.assign_explicit_operator()
    store.actor = replace(
        store.actor, membership=None, activation_complete=False, registration=None
    )
    for account in (TARGET, PEER):
        page = await history(store)(CREDENTIAL, account, REQUEST)
        assert page is not None
        assert page.snapshot.request_text == RAW_TEXT
        assert page.snapshot.note == RAW_NOTE
        assert page.snapshot.preview.source_json_raw == RAW_SOURCE
        assert page.snapshot.root.state == RequestState.PENDING_DECLINE
        assert page.snapshot.root.expires_at < page.observed_at
        assert page.revisions[0].decline_until is not None
        assert page.revisions[0].decline_until < page.observed_at
        assert page.snapshot.root.origin.trace_id == "legacy-trace"
        assert page.snapshot.root.origin.http_request_id is None
        assert RAW_TEXT not in repr(page)
        assert RAW_SOURCE not in repr(page.snapshot.preview)
        assert store.audit[-1].requested is not None
        assert store.audit[-1].requested.id == account


async def test_container_audit_distinguishes_missing_child_account_and_known_empty() -> None:
    store = RequestStore()
    store.assign_explicit_operator()
    assert await history(store)(CREDENTIAL, TARGET, uuid4()) is None
    inspected = store.audit[-1]
    assert inspected.outcome == OperatorAuditOutcome.READ
    assert inspected.results[0].id == TARGET
    stranger = uuid4()
    store.accounts.add(stranger)
    assert await history(store)(CREDENTIAL, stranger, REQUEST) is None
    assert await history(store)(CREDENTIAL, uuid4(), REQUEST) is None
    missing = store.audit[-1]
    assert missing.outcome == OperatorAuditOutcome.NOT_FOUND
    assert not missing.results
    assert await requests(store)(CREDENTIAL, uuid4(), OperatorRequestFilters()) is None
    empty = await requests(store)(CREDENTIAL, stranger, OperatorRequestFilters())
    assert empty is not None
    assert not empty.requests
    assert empty.anchor_request_id is None


async def test_relative_peer_direction_mode_state_and_halfopen_sent_filters() -> None:
    store = RequestStore()
    store.assign_explicit_operator()
    incoming = snapshot(uuid4(), incoming=True)
    store.snapshots[incoming.root.id] = incoming
    sent = await requests(store)(
        CREDENTIAL,
        TARGET,
        OperatorRequestFilters(
            peer_id=PEER,
            direction=OperatorRequestDirection.SENT,
            mode=DiscoveryMode.FIND_HELP,
            state=RequestState.PENDING_DECLINE,
            sent_from=root().sent_at,
        ),
    )
    assert sent is not None
    assert tuple(row.id for row in sent.requests) == (REQUEST,)
    received = await requests(store)(
        CREDENTIAL, TARGET, OperatorRequestFilters(direction=OperatorRequestDirection.RECEIVED)
    )
    assert received is not None
    assert tuple(row.id for row in received.requests) == (incoming.root.id,)
    for filters in (
        OperatorRequestFilters(peer_id=uuid4()),
        OperatorRequestFilters(mode=DiscoveryMode.OFFER_HELP),
        OperatorRequestFilters(state=RequestState.ACCEPTED),
        OperatorRequestFilters(sent_before=root().sent_at),
    ):
        page = await requests(store)(CREDENTIAL, TARGET, filters)
        assert page is not None
        assert not page.requests


async def test_root_keyset_actual_future_anchor_and_filter_hmac() -> None:
    store = RequestStore()
    store.assign_explicit_operator()
    store.snapshots = {}
    for index in range(1, OPERATOR_REQUEST_PAGE_SIZE + 3):
        value = snapshot(UUID(int=index))
        store.snapshots[value.root.id] = replace(
            value, root=replace(value.root, sent_at=NOW + timedelta(minutes=index))
        )
    first = await requests(store)(CREDENTIAL, TARGET, OperatorRequestFilters())
    assert first is not None
    assert first.next_cursor is not None
    assert len(first.requests) == OPERATOR_REQUEST_PAGE_SIZE
    assert first.anchor_sent_at is not None
    assert first.anchor_sent_at > first.observed_at
    newer = snapshot(uuid4())
    store.snapshots[newer.root.id] = replace(
        newer, root=replace(newer.root, sent_at=NOW + timedelta(days=3))
    )
    second = await requests(store)(CREDENTIAL, TARGET, OperatorRequestFilters(), first.next_cursor)
    assert second is not None
    assert len(second.requests) == len((1, 2))
    assert newer.root.id not in {row.id for row in second.requests}
    with pytest.raises(InvalidOperatorCursorError):
        await requests(store)(
            CREDENTIAL, TARGET, OperatorRequestFilters(peer_id=PEER), first.next_cursor
        )


async def test_all_raw_versions_and_page_only_acks_ignore_pointer_and_preserve_gaps() -> None:
    store = RequestStore()
    store.assign_explicit_operator()
    versions = tuple(range(1, OPERATOR_REQUEST_PAGE_SIZE + 4))
    store.revisions[REQUEST] = tuple(revision(v) for v in versions)
    store.acknowledgements = tuple(ack(v, viewer) for v in versions for viewer in (TARGET, PEER))
    first = await history(store)(CREDENTIAL, TARGET, REQUEST)
    assert first is not None
    assert first.next_cursor is not None
    assert first.anchor_version > first.snapshot.root.current_version
    assert len(first.acknowledgements) == OPERATOR_REQUEST_PAGE_SIZE * 2
    visible = {row.version for row in first.revisions}
    assert all(row.stored_version in visible for row in first.acknowledgements)
    second = await history(store)(CREDENTIAL, TARGET, REQUEST, first.next_cursor)
    assert second is not None
    assert tuple(row.version for row in second.revisions) == (3, 2, 1)
    assert len(second.acknowledgements) == len((1, 2, 3)) * 2
    store.revisions[REQUEST] = (revision(1), revision(3), revision(99))
    gaps = await history(store)(CREDENTIAL, TARGET, REQUEST)
    assert gaps is not None
    assert tuple(row.version for row in gaps.revisions) == (99, 3, 1)
    store.revisions[REQUEST] = (revision(1),)
    with pytest.raises(InvalidOperatorCursorError):
        await history(store)(CREDENTIAL, TARGET, REQUEST, first.next_cursor)


@pytest.mark.parametrize("read_history", [True, False])
async def test_live_operator_precedes_sources_and_expired_session_has_no_data(
    read_history: bool,
) -> None:
    store = RequestStore()
    operation = (
        history(store)(CREDENTIAL, TARGET, REQUEST)
        if read_history
        else requests(store)(CREDENTIAL, TARGET, OperatorRequestFilters())
    )
    with pytest.raises(OperatorAccessDeniedError):
        await operation
    assert store.private_queries == 0
    store.assign_explicit_operator()
    store.clock = store.actor.session.expires_at
    operation = (
        history(store)(CREDENTIAL, TARGET, REQUEST)
        if read_history
        else requests(store)(CREDENTIAL, TARGET, OperatorRequestFilters())
    )
    with pytest.raises(UnauthenticatedError):
        await operation
    assert not store.audit


@pytest.mark.parametrize("fault", ["owner", "order", "filter", "bounds"])
async def test_root_source_validation(fault: str) -> None:
    store = RequestStore()
    store.assign_explicit_operator()
    row = replace(root(), sender_id=uuid4(), recipient_id=uuid4()) if fault == "owner" else root()
    store.root_override = (
        (row, row)
        if fault == "order"
        else (row,) * (OPERATOR_REQUEST_PAGE_SIZE + 2)
        if fault == "bounds"
        else (row,)
    )
    filters = (
        OperatorRequestFilters(state=RequestState.ACCEPTED)
        if fault == "filter"
        else OperatorRequestFilters()
    )
    with pytest.raises(RuntimeError, match="source"):
        await requests(store)(CREDENTIAL, TARGET, filters)
    assert not store.audit


@pytest.mark.parametrize("fault", ["request", "order", "future", "bounds"])
async def test_revision_source_validation(fault: str) -> None:
    store = RequestStore()
    store.assign_explicit_operator()
    row = (
        revision(999)
        if fault == "future"
        else revision(1, uuid4())
        if fault == "request"
        else revision(1)
    )
    store.revision_override = (
        (row, row)
        if fault == "order"
        else (row,) * (OPERATOR_REQUEST_PAGE_SIZE + 2)
        if fault == "bounds"
        else (row,)
    )
    with pytest.raises(RuntimeError, match="source"):
        await history(store)(CREDENTIAL, TARGET, REQUEST)


@pytest.mark.parametrize("fault", ["count", "duplicate", "viewer", "version", "request"])
async def test_ack_source_validation_has_no_unbounded_or_foreign_views(fault: str) -> None:
    store = RequestStore()
    store.assign_explicit_operator()
    row = ack(1)
    if fault == "viewer":
        row = ack(1, uuid4())
    elif fault == "version":
        row = ack(99)
    elif fault == "request":
        row = ack(1, request_id=uuid4())
    store.ack_override = (
        (row,) * 7 if fault == "count" else (row, row) if fault == "duplicate" else (row,)
    )
    with pytest.raises(RuntimeError, match="ACK source"):
        await history(store)(CREDENTIAL, TARGET, REQUEST)
    assert not store.audit


async def test_account_and_head_sources_cannot_substitute_actual_participant() -> None:
    store = RequestStore()
    store.assign_explicit_operator()
    store.account_override = uuid4()
    with pytest.raises(RuntimeError, match="account source"):
        await requests(store)(CREDENTIAL, TARGET, OperatorRequestFilters())
    with pytest.raises(RuntimeError, match="account source"):
        await history(store)(CREDENTIAL, TARGET, REQUEST)
    store.account_override = None
    store.head_override = OperatorRequestHistoryHead(snapshot(uuid4()), 3)
    with pytest.raises(RuntimeError, match="actual owner or request"):
        await history(store)(CREDENTIAL, TARGET, REQUEST)


def test_raw_source_version_and_owned_disclosure_shapes() -> None:
    value = snapshot()
    with pytest.raises(ValueError, match="stored preview bound"):
        replace(value.preview, source_json_raw="é" * (OPERATOR_REQUEST_SOURCE_BYTES // 2 + 1))
    with pytest.raises(ValueError, match="owned preview source"):
        replace(value, preview=replace(value.preview, id=uuid4()))
    with pytest.raises(ValueError, match="positive current version"):
        replace(value.root, current_version=0)
    with pytest.raises(ValueError, match="positive stored revision"):
        revision(0)
    with pytest.raises(ValueError, match="actual positive source head"):
        OperatorRequestHistoryHead(value, 0)
    with pytest.raises(ValueError, match="actual version anchor"):
        OperatorRequestHistoryPosition(1, 2)
    original = ack(1)
    with pytest.raises(ValueError, match="linked disclosure source"):
        replace(original, viewer_id=uuid4())


def test_distinct_actor_grant_account_filter_and_history_cursor_scopes() -> None:
    scope = OperatorCursorScope(TARGET, 1)
    point = OperatorRequestPosition(NOW, REQUEST, NOW, REQUEST)
    digest = b"d" * 32
    token = CODEC.encode_roots(scope, TARGET, digest, point)
    assert CODEC.decode_roots(scope, TARGET, digest, token) == point
    for actual, account, query in (
        (OperatorCursorScope(uuid4(), 1), TARGET, digest),
        (OperatorCursorScope(TARGET, 2), TARGET, digest),
        (scope, uuid4(), digest),
        (scope, TARGET, b"x" * 32),
    ):
        with pytest.raises(InvalidOperatorCursorError):
            CODEC.decode_roots(actual, account, query, token)
    history_point = OperatorRequestHistoryPosition(3, 2)
    token = CODEC.encode_history(scope, TARGET, REQUEST, history_point)
    assert CODEC.decode_history(scope, TARGET, REQUEST, token) == history_point
    with pytest.raises(InvalidOperatorCursorError):
        CODEC.decode_history(scope, TARGET, uuid4(), token)
    for anchor in ("bad", "03"):
        bad = encode_cursor(
            CODEC.history,
            (
                "operator-connection-request-history-v1",
                str(TARGET),
                "1",
                str(TARGET),
                str(REQUEST),
                anchor,
                "2",
            ),
        )
        with pytest.raises(InvalidOperatorCursorError):
            CODEC.decode_history(scope, TARGET, REQUEST, bad)
    malformed = encode_cursor(
        CODEC.roots,
        (
            "operator-connection-requests-v1",
            str(TARGET),
            "1",
            str(TARGET),
            digest.hex(),
            "bad-date",
            str(REQUEST),
            NOW.isoformat(),
            str(REQUEST),
        ),
    )
    with pytest.raises(InvalidOperatorCursorError):
        CODEC.decode_roots(scope, TARGET, digest, malformed)
    with pytest.raises(ValueError, match="configured32-byte"):
        FernetOperatorRequestCursorCodec.from_key(b"short")
    with pytest.raises(ValueError, match="actual query HMAC"):
        CODEC.encode_roots(scope, TARGET, b"short", point)
    with pytest.raises(ValueError, match="nonempty half-open"):
        OperatorRequestFilters(sent_from=NOW, sent_before=NOW)
    with pytest.raises(ValueError, match="actual sent metadata anchor"):
        OperatorRequestPosition(NOW, REQUEST, NOW + timedelta(seconds=1), REQUEST)
