from dataclasses import replace
from datetime import timedelta
from uuid import UUID, uuid4

import pytest

from studymate.application.errors import StorageUnavailableError
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.operator.authority import OperatorAccessDeniedError
from studymate.application.operator.cursors import InvalidOperatorCursorError
from studymate.application.operator.timeline import (
    ReadOperatorAudit,
    ReadOperatorEvent,
    SearchOperatorEvents,
)
from studymate.application.operator.timeline_ports import (
    OperatorEventFilters,
)
from studymate.domain.operator.audit import (
    OPERATOR_EVENT_PAGE_SIZE,
    OperatorAction,
    OperatorAuditOutcome,
    OperatorResourceKind,
    OperatorResourceRef,
)
from studymate.domain.operator.timeline import (
    OperatorEventOrigin,
    OperatorEventSource,
    OperatorSourceKind,
    OperatorTimelineEvent,
)
from studymate.infrastructure.operator.timeline_cursors import FernetOperatorEventCursorCodec
from tests.unit.identity_store import CREDENTIAL, NOW
from tests.unit.operator.test_authorized_reads import FINGERPRINTER, HASHER
from tests.unit.operator.timeline_store import TimelineStore, event

CODEC = FernetOperatorEventCursorCodec.from_key(b"t" * 32)


def search(store: TimelineStore) -> SearchOperatorEvents:
    return SearchOperatorEvents(store, HASHER, FINGERPRINTER, CODEC)


async def test_actual_event_and_original_audit_are_audited_with_new_exact_source_refs() -> None:
    store = TimelineStore()
    store.assign_explicit_operator()
    original = store.original_audit()
    actual = store.events[0]
    assert await ReadOperatorEvent(store, HASHER)(CREDENTIAL, actual.id) == actual
    event_audit = store.audit[-1]
    assert event_audit.action == OperatorAction.READ_EVENT
    assert store.audit[-1].results == (OperatorResourceRef(OperatorResourceKind.EVENT, actual.id),)
    assert await ReadOperatorAudit(store, HASHER)(CREDENTIAL, original.audit.id) == original
    audit_inspection = store.audit[-1]
    assert audit_inspection.action == OperatorAction.READ_AUDIT
    assert store.audit[-1].results == (
        OperatorResourceRef(OperatorResourceKind.AUDIT, original.audit.id),
    )


async def test_missing_read_commits_not_found_not_a_false_detail() -> None:
    store = TimelineStore()
    store.assign_explicit_operator()
    assert await ReadOperatorEvent(store, HASHER)(CREDENTIAL, uuid4()) is None
    assert await ReadOperatorAudit(store, HASHER)(CREDENTIAL, uuid4()) is None
    assert all(
        row.outcome == OperatorAuditOutcome.NOT_FOUND and not row.results for row in store.audit
    )


async def test_bounded_event_search_filter_bound_keyset_and_only_visible_ids_in_audit() -> None:
    store = TimelineStore()
    store.assign_explicit_operator()
    store.events = tuple(
        event(event_id=UUID(int=i + 1)) for i in range(OPERATOR_EVENT_PAGE_SIZE + 2)
    )
    first = await search(store)(CREDENTIAL, OperatorEventFilters())
    assert len(first.events) == OPERATOR_EVENT_PAGE_SIZE
    assert first.next_cursor is not None
    assert len(store.audit[-1].results) == OPERATOR_EVENT_PAGE_SIZE
    second = await search(store)(CREDENTIAL, OperatorEventFilters(), first.next_cursor)
    assert {row.id for row in first.events + second.events} == {row.id for row in store.events}
    assert second.next_cursor is None
    assert store.audit[-1].query_fingerprint is not None
    with pytest.raises(InvalidOperatorCursorError):
        await search(store)(
            CREDENTIAL, OperatorEventFilters(subject_account_id=uuid4()), first.next_cursor
        )


async def test_anchor_is_search_predicate_not_commit_watermark_or_newer_commits_promise() -> None:
    store = TimelineStore()
    store.assign_explicit_operator()
    rows = tuple(event(event_id=UUID(int=i + 1)) for i in range(OPERATOR_EVENT_PAGE_SIZE + 1))
    store.events = rows
    first = await search(store)(CREDENTIAL, OperatorEventFilters())
    assert first.next_cursor is not None
    # A late visible insertion with older metadata can enter a later keyset page.
    late = replace(event(), occurred_at=rows[0].occurred_at - timedelta(seconds=1))
    newer = replace(event(), occurred_at=NOW + timedelta(seconds=1))
    store.events += (late, newer)
    second = await search(store)(CREDENTIAL, OperatorEventFilters(), first.next_cursor)
    assert late.id in {row.id for row in second.events}
    assert newer.id not in {row.id for row in second.events}
    assert second.search_anchor_at == first.search_anchor_at


@pytest.mark.parametrize("denial", ["missing", "revoked", "banned", "deleted", "expired"])
async def test_all_timeline_reads_require_actual_current_explicit_operator_role(
    denial: str,
) -> None:
    store = TimelineStore()
    if denial != "missing":
        store.assign_explicit_operator()
    if denial == "revoked":
        assert store.access is not None
        store.access = replace(store.access, active=False)
    elif denial == "banned":
        store.actor = replace(store.actor, banned=True)
    elif denial == "deleted":
        store.actor = replace(store.actor, deleted_at=NOW)
    elif denial == "expired":
        store.clock = store.actor.session.expires_at
    error = UnauthenticatedError if denial in {"deleted", "expired"} else OperatorAccessDeniedError
    with pytest.raises(error):
        await search(store)(CREDENTIAL, OperatorEventFilters())
    with pytest.raises(error):
        await ReadOperatorEvent(store, HASHER)(CREDENTIAL, uuid4())
    with pytest.raises(error):
        await ReadOperatorAudit(store, HASHER)(CREDENTIAL, uuid4())
    assert store.private_queries == 0
    assert not store.audit


@pytest.mark.parametrize("kind", ["search", "event", "audit"])
@pytest.mark.parametrize("fault", ["audit_storage", "deadline"])
async def test_same_transaction_audit_or_final_session_failure_returns_no_data(
    kind: str, fault: str
) -> None:
    store = TimelineStore()
    store.assign_explicit_operator()
    original = store.original_audit()
    store.fail_audit = fault == "audit_storage"
    store.expire_after_audit = fault == "deadline"
    error = StorageUnavailableError if fault == "audit_storage" else UnauthenticatedError
    with pytest.raises(error):
        await read_kind(store, kind, original.audit.id)
    assert not store.audit


async def read_kind(store: TimelineStore, kind: str, audit_id: UUID) -> None:
    if kind == "search":
        await search(store)(CREDENTIAL, OperatorEventFilters())
    elif kind == "event":
        await ReadOperatorEvent(store, HASHER)(CREDENTIAL, store.events[0].id)
    else:
        await ReadOperatorAudit(store, HASHER)(CREDENTIAL, audit_id)


@pytest.mark.parametrize("kind", ["unbounded", "order", "future", "wrong_event", "wrong_audit"])
async def test_broken_source_projections_fail_before_committing_false_audit(kind: str) -> None:
    store = TimelineStore()
    store.assign_explicit_operator()
    original = store.original_audit()
    missing = uuid4()
    if kind == "unbounded":
        store.event_rows = tuple(event() for _ in range(OPERATOR_EVENT_PAGE_SIZE + 2))
    elif kind == "order":
        store.event_rows = (store.events[0], store.events[0])
    elif kind == "future":
        store.event_rows = (replace(event(), occurred_at=NOW + timedelta(seconds=1)),)
    elif kind == "wrong_event":
        store.event_map[missing] = store.events[0]
    else:
        store.originals[missing] = original
    with pytest.raises(RuntimeError, match=r"bounded|ordering|actual requested"):
        await broken_source(store, kind, missing)
    assert not store.audit


async def broken_source(store: TimelineStore, kind: str, missing: UUID) -> None:
    if kind == "wrong_event":
        await ReadOperatorEvent(store, HASHER)(CREDENTIAL, missing)
    elif kind == "wrong_audit":
        await ReadOperatorAudit(store, HASHER)(CREDENTIAL, missing)
    else:
        await search(store)(CREDENTIAL, OperatorEventFilters())


@pytest.mark.parametrize(
    "fault",
    [
        "origin_context",
        "trace_pair",
        "trace_zero",
        "span_bad",
        "source_owner",
        "source_version",
        "source_convo",
        "source_recipient",
        "source_grant",
        "source_account",
        "schema",
        "extra_source",
        "kind_source",
        "extra_initiator",
    ],
)
def test_finite_source_and_origin_shapes_reject_invented_links(fault: str) -> None:
    actual = event()
    source = actual.sources[0]
    with pytest.raises(ValueError, match=r"source|origin|Canonical|schema|event"):
        invalid_value(actual, source, fault)


def invalid_value(actual: OperatorTimelineEvent, source: OperatorEventSource, fault: str) -> None:
    if fault in {"origin_context", "trace_pair", "trace_zero", "span_bad"}:
        invalid_origin(fault)
    elif fault == "source_owner":
        replace(source, owner_id=None)
    elif fault == "source_version":
        replace(source, version=True)
    elif fault == "source_convo":
        replace(source, conversation_id=uuid4())
    elif fault == "source_recipient":
        replace(source, related_account_id=uuid4())
    elif fault == "source_grant":
        replace(source, operator_access_version=1)
    elif fault == "source_account":
        OperatorEventSource(OperatorSourceKind.ACCOUNT, uuid4(), uuid4())
    elif fault == "schema":
        replace(actual, schema_version=True)
    elif fault == "extra_source":
        replace(actual, sources=(source, source))
    elif fault == "kind_source":
        replace(actual, subject_account_id=uuid4())
    else:
        replace(actual, initiator_account_id=uuid4())


def invalid_origin(fault: str) -> None:
    if fault == "origin_context":
        OperatorEventOrigin(action_id=uuid4())
    elif fault == "trace_pair":
        OperatorEventOrigin(uuid4(), trace_id="a" * 32)
    elif fault == "trace_zero":
        OperatorEventOrigin(uuid4(), trace_id="0" * 32, span_id="b" * 16)
    elif fault == "span_bad":
        OperatorEventOrigin(uuid4(), trace_id="a" * 32, span_id="unsafe")
