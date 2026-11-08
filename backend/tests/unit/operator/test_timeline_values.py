import json
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest

from studymate.application.operator.cursors import InvalidOperatorCursorError, OperatorCursorScope
from studymate.application.operator.timeline_ports import (
    OperatorEventFilters,
    OperatorEventPosition,
)
from studymate.domain.operator.audit import (
    OPERATOR_EVENT_PAGE_SIZE,
    OperatorAction,
    OperatorAuditOutcome,
    OperatorResourceKind,
    OperatorResourceRef,
)
from studymate.domain.operator.timeline import (
    CONVERSATION_SOURCES,
    EVENT_SOURCES,
    VERSIONED_SOURCES,
    OperatorEventKind,
    OperatorEventOrigin,
    OperatorEventSource,
    OperatorSourceKind,
    OperatorTimelineEvent,
)
from studymate.infrastructure.operator.cursors import FernetOperatorCursorCodec
from studymate.infrastructure.operator.timeline_cursors import FernetOperatorEventCursorCodec
from tests.unit.identity_store import NOW
from tests.unit.operator.timeline_store import TimelineStore, event

CODEC = FernetOperatorEventCursorCodec.from_key(b"t" * 32)


@pytest.mark.parametrize("kind", list(OperatorEventKind))
def test_every_actual_event_kind_has_finite_owned_version_and_conversation_source_shape(
    kind: OperatorEventKind,
) -> None:
    source_kind = EVENT_SOURCES[kind]
    owner = uuid4()
    source = OperatorEventSource(
        source_kind,
        owner
        if source_kind
        in {
            OperatorSourceKind.ACCOUNT,
            OperatorSourceKind.PROFILE,
            OperatorSourceKind.HELP,
            OperatorSourceKind.PHOTO,
            OperatorSourceKind.VISIBILITY,
        }
        else uuid4(),
        owner,
        version=1 if source_kind in VERSIONED_SOURCES else None,
        conversation_id=uuid4() if source_kind in CONVERSATION_SOURCES else None,
        related_account_id=uuid4()
        if source_kind in {OperatorSourceKind.REQUEST, OperatorSourceKind.LIFECYCLE}
        else None,
        operator_access_version=1 if source_kind == OperatorSourceKind.OPERATOR_AUDIT else None,
    )
    actual = replace(event(owner=owner), kind=kind, sources=(source,))
    assert actual.sources[0].owner_id == actual.subject_account_id
    if kind in {OperatorEventKind.GOAL_SAVED, OperatorEventKind.GOAL_COMPLETED}:
        catalogue = OperatorEventSource(OperatorSourceKind.SUBJECT, uuid4(), None)
        assert len(replace(actual, sources=(source, catalogue)).sources) == len((source, catalogue))


@pytest.mark.parametrize(
    "fault", ["recipient", "grant", "subjectowner", "extra_catalogue", "no_source"]
)
def test_source_specific_constraints_do_not_invent_identity_or_grant(fault: str) -> None:
    actual = event()
    with pytest.raises(ValueError, match=r"source|recipient|grant|subject"):
        invalid_source(actual, fault)


def invalid_source(actual: OperatorTimelineEvent, fault: str) -> None:
    if fault == "recipient":
        OperatorEventSource(
            OperatorSourceKind.REQUEST,
            uuid4(),
            actual.subject_account_id,
            version=1,
            related_account_id=actual.subject_account_id,
        )
    elif fault == "grant":
        OperatorEventSource(
            OperatorSourceKind.OPERATOR_AUDIT,
            uuid4(),
            actual.subject_account_id,
            operator_access_version=0,
        )
    elif fault == "subjectowner":
        OperatorEventSource(OperatorSourceKind.SUBJECT, uuid4(), actual.subject_account_id)
    elif fault == "extra_catalogue":
        replace(
            actual,
            sources=(
                actual.sources[0],
                OperatorEventSource(
                    OperatorSourceKind.ACCOUNT, actual.subject_account_id, actual.subject_account_id
                ),
            ),
        )
    else:
        replace(actual, sources=())


@pytest.mark.parametrize(
    "action", [OperatorAction.SEARCH_EVENTS, OperatorAction.READ_EVENT, OperatorAction.READ_AUDIT]
)
def test_new_audit_actions_keep_exact_result_shape_and_nonfound_policy(
    action: OperatorAction,
) -> None:
    store = TimelineStore()
    store.assign_explicit_operator()
    audit = store.original_audit().audit
    if action == OperatorAction.SEARCH_EVENTS:
        valid = replace(
            audit,
            action=action,
            requested=None,
            outcome=OperatorAuditOutcome.SEARCH,
            results=(),
            query_fingerprint=b"h" * 32,
        )
        assert valid.outcome == OperatorAuditOutcome.SEARCH
        with pytest.raises(ValueError, match="bounded"):
            replace(
                valid,
                results=tuple(
                    OperatorResourceRef(OperatorResourceKind.EVENT, uuid4())
                    for _ in range(OPERATOR_EVENT_PAGE_SIZE + 1)
                ),
            )
    else:
        requested = OperatorResourceRef(
            OperatorResourceKind.EVENT
            if action == OperatorAction.READ_EVENT
            else OperatorResourceKind.AUDIT,
            uuid4(),
        )
        valid = replace(audit, action=action, requested=requested, results=(requested,))
        assert replace(valid, results=(), outcome=OperatorAuditOutcome.NOT_FOUND).results == ()
        with pytest.raises(ValueError, match="actual returned"):
            replace(valid, results=())


@pytest.mark.parametrize("fault", ["trace", "zero_trace", "range", "naive"])
def test_search_filters_have_bounded_metadata_only_and_aware_halfopen_time(fault: str) -> None:
    with pytest.raises(ValueError, match=r"trace|interval|timezone"):
        invalid_filter(fault)


def invalid_filter(fault: str) -> None:
    if fault == "trace":
        OperatorEventFilters(trace_id="raw private query")
    elif fault == "zero_trace":
        OperatorEventFilters(trace_id="0" * 32)
    elif fault == "range":
        OperatorEventFilters(occurred_from=NOW, occurred_before=NOW)
    else:
        OperatorEventFilters(occurred_from=NOW.replace(tzinfo=None))


def test_filter_hmac_canonicalizes_same_utc_window_and_includes_all_bounded_refs() -> None:
    source = OperatorEventFilters(
        uuid4(),
        uuid4(),
        uuid4(),
        "a" * 32,
        OperatorEventKind.FEEDBACK_SAVED,
        NOW - timedelta(hours=1),
        NOW,
    )
    assert source.fingerprint_parts()[1] == str(source.subject_account_id)
    assert source.fingerprint_parts()[2] == str(source.http_request_id)
    assert source.fingerprint_parts()[3] == str(source.action_id)
    assert source.fingerprint_parts()[-1] == NOW.isoformat()
    assert "a" * 32 not in repr(source)


def test_event_cursor_bound_to_actor_grant_filter_and_resource_purpose() -> None:
    scope = OperatorCursorScope(uuid4(), 1)
    position = OperatorEventPosition(NOW, NOW - timedelta(seconds=1), uuid4())
    token = CODEC.encode_events(scope, b"h" * 32, position)
    assert CODEC.decode_events(scope, b"h" * 32, token, NOW) == position
    for actor, digest in (
        (replace(scope, account_id=uuid4()), b"h" * 32),
        (replace(scope, access_version=2), b"h" * 32),
        (scope, b"x" * 32),
        (scope, b"bad"),
    ):
        with pytest.raises(InvalidOperatorCursorError):
            CODEC.decode_events(actor, digest, token, NOW)
    account_codec = FernetOperatorCursorCodec.from_key(b"t" * 32)
    alien = account_codec.accounts.encrypt(b"[]").decode("ascii")
    with pytest.raises(InvalidOperatorCursorError):
        CODEC.decode_events(scope, b"h" * 32, alien, NOW)
    with pytest.raises(InvalidOperatorCursorError):
        CODEC.decode_events(scope, b"h" * 32, token, NOW - timedelta(seconds=1))
    with pytest.raises(ValueError, match="32-byte"):
        FernetOperatorEventCursorCodec.from_key(b"bad")
    with pytest.raises(ValueError, match="query HMAC"):
        CODEC.encode_events(scope, b"bad", position)


@pytest.mark.parametrize("fault", ["date", "naive", "position", "uuid"])
def test_valid_crypto_with_invalid_cursor_metadata_is_not_accepted(fault: str) -> None:
    scope = OperatorCursorScope(uuid4(), 1)
    parts = [
        "operator-events-v1",
        str(scope.account_id),
        str(scope.access_version),
        (b"h" * 32).hex(),
        NOW.isoformat(),
        (NOW - timedelta(seconds=1)).isoformat(),
        str(uuid4()),
    ]
    if fault == "date":
        parts[4] = "bad date"
    elif fault == "naive":
        parts[4] = NOW.replace(tzinfo=None).isoformat()
    elif fault == "position":
        parts[5] = (NOW + timedelta(seconds=1)).isoformat()
    else:
        parts[6] = "invalid uuid"
    token = CODEC.cipher.encrypt(json.dumps(parts).encode("ascii")).decode("ascii")
    with pytest.raises(InvalidOperatorCursorError):
        CODEC.decode_events(scope, b"h" * 32, token, NOW)


def test_origin_pairs_are_optional_technical_refs_not_invented_context() -> None:
    assert OperatorEventOrigin().http_request_id is None
