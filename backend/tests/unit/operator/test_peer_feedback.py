from dataclasses import replace
from datetime import timedelta
from uuid import UUID, uuid4

import pytest

from studymate.application.errors import StorageUnavailableError
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.operator.authority import OperatorAccessDeniedError
from studymate.application.operator.cursors import InvalidOperatorCursorError, OperatorCursorScope
from studymate.application.operator.feedback_ports import (
    OperatorFeedbackDirection,
    OperatorFeedbackFilters,
    OperatorFeedbackHistoryHead,
    OperatorFeedbackHistoryPosition,
    OperatorFeedbackTimePosition,
)
from studymate.application.operator.peer_feedback import (
    OperatorFeedbackHistoryPage,
    OperatorFeedbackRemovalsPage,
    OperatorFeedbackRootsPage,
    ReadOperatorFeedback,
    ReadOperatorFeedbackHistory,
    ReadOperatorFeedbackRemovals,
)
from studymate.domain.operator.audit import OperatorAuditOutcome
from studymate.domain.operator.peer_feedback import (
    MAX_OPERATOR_FEEDBACK_TEXT,
    OPERATOR_FEEDBACK_PAGE_SIZE,
)
from studymate.infrastructure.operator.cursors import encode_cursor
from studymate.infrastructure.operator.feedback_cursors import FernetOperatorFeedbackCursorCodec
from tests.unit.identity_store import CREDENTIAL, NOW
from tests.unit.operator.feedback_store import (
    FEEDBACK,
    PEER,
    RAW_NOTE,
    RAW_REASON,
    FeedbackStore,
    removal,
    revision,
    root,
)
from tests.unit.operator.store import TARGET
from tests.unit.operator.test_authorized_reads import FINGERPRINTER, HASHER

CODEC = FernetOperatorFeedbackCursorCodec.from_key(b"f" * 32)


def roots(store: FeedbackStore) -> ReadOperatorFeedback:
    return ReadOperatorFeedback(store, HASHER, FINGERPRINTER, CODEC)


def history(store: FeedbackStore) -> ReadOperatorFeedbackHistory:
    return ReadOperatorFeedbackHistory(store, HASHER, CODEC)


def removals(store: FeedbackStore) -> ReadOperatorFeedbackRemovals:
    return ReadOperatorFeedbackRemovals(store, HASHER, CODEC)


async def read(
    store: FeedbackStore, kind: str, account: UUID = TARGET, feedback: UUID = FEEDBACK
) -> OperatorFeedbackRootsPage | OperatorFeedbackHistoryPage | OperatorFeedbackRemovalsPage | None:
    if kind == "roots":
        return await roots(store)(CREDENTIAL, account, OperatorFeedbackFilters())
    if kind == "history":
        return await history(store)(CREDENTIAL, account, feedback)
    return await removals(store)(CREDENTIAL, account, feedback)


async def test_both_actual_participants_raw_history_max_all_and_private_content() -> None:
    store = FeedbackStore()
    store.assign_explicit_operator()
    store.actor = replace(
        store.actor, membership=None, activation_complete=False, registration=None
    )
    store.revisions[FEEDBACK] = tuple(
        revision(index) for index in range(1, OPERATOR_FEEDBACK_PAGE_SIZE + 4)
    )
    for account in (TARGET, PEER):
        page = await history(store)(CREDENTIAL, account, FEEDBACK)
        assert page is not None
        assert page.next_cursor is not None
        assert page.root.current_version == 1
        assert page.anchor_version == max(row.version for row in store.revisions[FEEDBACK])
        assert len(page.revisions) == OPERATOR_FEEDBACK_PAGE_SIZE
        assert page.revisions[0].changed_at < page.revisions[-1].changed_at
        assert page.revisions[0].team_note == RAW_NOTE
        assert page.revisions[0].descriptors == ("supportive", "easy_to_communicate")
        assert page.revisions[0].worked_confirmation_id == revision().worked_confirmation_id
        assert RAW_NOTE not in repr(page)
        assert RAW_NOTE not in repr(page.revisions[0])
    assert page is not None
    assert page.next_cursor is not None
    last = await history(store)(CREDENTIAL, PEER, FEEDBACK, page.next_cursor)
    assert last is not None
    assert tuple(row.version for row in last.revisions) == (3, 2, 1)
    assert not last.next_cursor
    store.revisions[FEEDBACK] = (revision(1), revision(7), revision(99))
    gaps = await history(store)(CREDENTIAL, TARGET, FEEDBACK)
    assert gaps is not None
    assert tuple(row.version for row in gaps.revisions) == (99, 7, 1)
    assert len(store.audit) == len((TARGET, PEER, last, gaps))


async def test_removals_separate_unbounded_history_pointer_not_all_records() -> None:
    store = FeedbackStore()
    store.assign_explicit_operator()
    store.removals = tuple(removal(index) for index in range(OPERATOR_FEEDBACK_PAGE_SIZE + 3))
    store.roots[FEEDBACK] = replace(root(), current_removal_id=store.removals[0].id)
    first = await removals(store)(CREDENTIAL, TARGET, FEEDBACK)
    assert first is not None
    assert first.next_cursor is not None
    assert first.anchor_removed_at is not None
    assert first.anchor_removed_at > NOW
    assert first.root.current_removal_id != first.removals[0].id
    assert len(first.removals) == OPERATOR_FEEDBACK_PAGE_SIZE
    assert RAW_REASON not in repr(first)
    store.removals = (*store.removals, replace(removal(100), removed_at=NOW + timedelta(days=2)))
    last = await removals(store)(CREDENTIAL, TARGET, FEEDBACK, first.next_cursor)
    assert last is not None
    assert len(last.removals) == len((1, 2, 3))
    assert last.anchor_removal_id == first.anchor_removal_id
    assert not last.next_cursor
    store.removals = ()
    empty = await removals(store)(CREDENTIAL, TARGET, FEEDBACK)
    assert empty is not None
    assert not empty.removals
    assert empty.anchor_removal_id is None


async def test_current_pointer_metadata_filters_and_actual_changed_anchor() -> None:
    store = FeedbackStore()
    store.assign_explicit_operator()
    store.roots = {}
    for index in range(OPERATOR_FEEDBACK_PAGE_SIZE + 2):
        row = root(UUID(int=100 + index), peer=UUID(int=9000 + index))
        store.roots[row.id] = replace(row, current_changed_at=NOW + timedelta(minutes=index))
    filters = OperatorFeedbackFilters(
        direction=OperatorFeedbackDirection.GIVEN, removed=False, changed_from=NOW
    )
    first = await roots(store)(CREDENTIAL, TARGET, filters)
    assert first is not None
    assert first.next_cursor is not None
    assert first.anchor_changed_at is not None
    assert first.anchor_changed_at > first.observed_at
    last = await roots(store)(CREDENTIAL, TARGET, filters, first.next_cursor)
    assert last is not None
    assert len(last.feedback) == len((1, 2))
    incoming = root(uuid4(), received=True)
    store.roots[incoming.id] = replace(incoming, current_removal_id=uuid4())
    received = await roots(store)(
        CREDENTIAL,
        TARGET,
        OperatorFeedbackFilters(
            peer_id=PEER,
            direction=OperatorFeedbackDirection.RECEIVED,
            removed=True,
            changed_before=NOW + timedelta(seconds=1),
        ),
    )
    assert received is not None
    assert received.feedback == (store.roots[incoming.id],)
    for query in (
        OperatorFeedbackFilters(peer_id=uuid4()),
        OperatorFeedbackFilters(changed_before=NOW),
    ):
        empty = await roots(store)(CREDENTIAL, TARGET, query)
        assert empty is not None
        assert not empty.feedback
        assert empty.anchor_feedback_id is None
    assert not OperatorFeedbackFilters().matches(root(), uuid4())


@pytest.mark.parametrize("kind", ["roots", "history", "removals"])
async def test_missing_parent_and_foreign_child_truthful_container_audit(kind: str) -> None:
    store = FeedbackStore()
    store.assign_explicit_operator()
    assert await read(store, kind, uuid4()) is None
    missing = store.audit[-1]
    assert missing.outcome == OperatorAuditOutcome.NOT_FOUND
    assert not missing.results
    if kind != "roots":
        assert await read(store, kind, feedback=uuid4()) is None
        assert store.audit[-1].outcome == OperatorAuditOutcome.READ
        foreign = uuid4()
        store.accounts.add(foreign)
        assert await read(store, kind, foreign) is None
        assert store.audit[-1].results[0].id == foreign


@pytest.mark.parametrize("kind", ["roots", "history", "removals"])
@pytest.mark.parametrize("fault", ["role", "audit", "expiry"])
async def test_live_guard_and_atomic_audit_hold_all_data(kind: str, fault: str) -> None:
    store = FeedbackStore()
    if fault != "role":
        store.assign_explicit_operator()
    store.fail_audit = fault == "audit"
    store.expire_after_audit = fault == "expiry"
    error = (
        OperatorAccessDeniedError
        if fault == "role"
        else UnauthenticatedError
        if fault == "expiry"
        else StorageUnavailableError
    )
    with pytest.raises(error):
        await read(store, kind)
    assert not store.audit
    if fault == "role":
        assert store.private_queries == 0


@pytest.mark.parametrize("kind", ["roots", "history", "removals"])
async def test_account_source_cannot_switch_requested_identity(kind: str) -> None:
    store = FeedbackStore()
    store.assign_explicit_operator()
    store.account_override = uuid4()
    with pytest.raises(RuntimeError, match="another account"):
        await read(store, kind)
    assert not store.audit


@pytest.mark.parametrize(
    "fault",
    [
        "head",
        "child",
        "roots_size",
        "roots_order",
        "roots_filter",
        "revisions_size",
        "revisions_owner",
        "revisions_order",
        "removals_size",
        "removals_source",
        "removals_order",
    ],
)
async def test_source_scopes_windows_and_ordering_fail_closed(fault: str) -> None:
    store = FeedbackStore()
    store.assign_explicit_operator()
    kind = (
        "roots"
        if fault.startswith("roots")
        else "removals"
        if fault.startswith("removals") or fault == "child"
        else "history"
    )
    if fault == "head":
        store.head_override = OperatorFeedbackHistoryHead(root(uuid4()), 1)
    elif fault == "child":
        store.root_override = root(uuid4())
    elif fault == "roots_size":
        store.root_rows = tuple(
            root(UUID(int=100 + index)) for index in range(OPERATOR_FEEDBACK_PAGE_SIZE + 2)
        )
    elif fault == "roots_order":
        store.root_rows = (root(), root())
    elif fault == "roots_filter":
        store.root_rows = (root(received=True),)
    elif fault == "revisions_size":
        store.revision_rows = tuple(
            revision(index) for index in range(1, OPERATOR_FEEDBACK_PAGE_SIZE + 3)
        )
    elif fault == "revisions_owner":
        store.revision_rows = (replace(revision(), conversation_id=uuid4()),)
    elif fault == "revisions_order":
        store.revision_rows = (revision(), revision())
    elif fault == "removals_size":
        store.removal_rows = tuple(
            removal(index) for index in range(OPERATOR_FEEDBACK_PAGE_SIZE + 2)
        )
    elif fault == "removals_source":
        store.removal_rows = (removal(feedback_id=uuid4()),)
    else:
        value = removal()
        store.removal_rows = (value, value)
    call = (
        roots(store)(
            CREDENTIAL, TARGET, OperatorFeedbackFilters(direction=OperatorFeedbackDirection.GIVEN)
        )
        if kind == "roots"
        else read(store, kind)
    )
    with pytest.raises(RuntimeError):
        await call
    assert not store.audit


async def test_cursor_boundaries_distinct_purposes_and_impossible_history_anchor() -> None:
    scope = OperatorCursorScope(uuid4(), 1)
    digest = await FINGERPRINTER.fingerprint(OperatorFeedbackFilters().fingerprint_parts())
    position = OperatorFeedbackTimePosition(NOW, UUID(int=2), NOW, UUID(int=1))
    token = CODEC.encode_roots(scope, TARGET, digest, position)
    history_position = OperatorFeedbackHistoryPosition(3, 2)
    ht = CODEC.encode_history(scope, TARGET, FEEDBACK, history_position)
    rt = CODEC.encode_removals(scope, TARGET, FEEDBACK, position)
    assert CODEC.decode_roots(scope, TARGET, digest, token) == position
    assert CODEC.decode_history(scope, TARGET, FEEDBACK, ht) == history_position
    assert CODEC.decode_removals(scope, TARGET, FEEDBACK, rt) == position
    for actor, account, fingerprint, cursor in (
        (replace(scope, account_id=uuid4()), TARGET, digest, token),
        (replace(scope, access_version=2), TARGET, digest, token),
        (scope, uuid4(), digest, token),
        (scope, TARGET, b"x" * 32, token),
        (scope, TARGET, b"short", token),
        (scope, TARGET, digest, rt),
    ):
        with pytest.raises(InvalidOperatorCursorError):
            CODEC.decode_roots(actor, account, fingerprint, cursor)
    for actor, account, feedback, cursor in (
        (replace(scope, account_id=uuid4()), TARGET, FEEDBACK, ht),
        (replace(scope, access_version=2), TARGET, FEEDBACK, ht),
        (scope, uuid4(), FEEDBACK, ht),
        (scope, TARGET, uuid4(), ht),
        (scope, TARGET, FEEDBACK, rt),
    ):
        with pytest.raises(InvalidOperatorCursorError):
            CODEC.decode_history(actor, account, feedback, cursor)
    for actor, account, feedback, cursor in (
        (replace(scope, access_version=2), TARGET, FEEDBACK, rt),
        (scope, uuid4(), FEEDBACK, rt),
        (scope, TARGET, uuid4(), rt),
        (scope, TARGET, FEEDBACK, ht),
    ):
        with pytest.raises(InvalidOperatorCursorError):
            CODEC.decode_removals(actor, account, feedback, cursor)
    with pytest.raises(ValueError, match="HMAC"):
        CODEC.encode_roots(scope, TARGET, b"short", position)
    with pytest.raises(ValueError, match="32-byte"):
        FernetOperatorFeedbackCursorCodec.from_key(b"short")
    for cipher, purpose, child in (
        (CODEC.roots, "operator-feedback-roots-v1", digest.hex()),
        (CODEC.removals, "operator-feedback-removals-v1", str(FEEDBACK)),
    ):
        malformed = encode_cursor(
            cipher,
            (
                purpose,
                str(scope.account_id),
                "1",
                str(TARGET),
                child,
                "bad-time",
                str(uuid4()),
                NOW.isoformat(),
                str(uuid4()),
            ),
        )
        if purpose == "operator-feedback-roots-v1":
            with pytest.raises(InvalidOperatorCursorError):
                CODEC.decode_roots(scope, TARGET, digest, malformed)
        else:
            with pytest.raises(InvalidOperatorCursorError):
                CODEC.decode_removals(scope, TARGET, FEEDBACK, malformed)
    for anchor, before in (("bad", "2"), ("3", "02"), ("3", "4")):
        malformed = encode_cursor(
            CODEC.history,
            (
                "operator-feedback-history-v1",
                str(scope.account_id),
                "1",
                str(TARGET),
                str(FEEDBACK),
                anchor,
                before,
            ),
        )
        with pytest.raises(InvalidOperatorCursorError):
            CODEC.decode_history(scope, TARGET, FEEDBACK, malformed)
    store = FeedbackStore()
    store.assign_explicit_operator()
    assert store.access is not None
    current = OperatorCursorScope(store.access.account_id, store.access.version)
    impossible = CODEC.encode_history(
        current, TARGET, FEEDBACK, OperatorFeedbackHistoryPosition(99, 98)
    )
    with pytest.raises(InvalidOperatorCursorError):
        await history(store)(CREDENTIAL, TARGET, FEEDBACK, impossible)


@pytest.mark.parametrize("version", [0, True, 1 << 31])
def test_raw_version_boundaries(version: int) -> None:
    with pytest.raises(ValueError, match="bounded source version"):
        replace(revision(), version=version)
    with pytest.raises(ValueError, match="bounded source version"):
        OperatorFeedbackHistoryPosition(version, version)
    with pytest.raises(ValueError, match="bounded source version"):
        replace(removal(), operator_access_version=version)


def test_raw_notes_reasons_and_source_boundaries_never_normalize() -> None:
    assert revision().team_note == RAW_NOTE
    assert removal().reason == RAW_REASON
    assert replace(revision(), team_note="あ" * MAX_OPERATOR_FEEDBACK_TEXT).team_note is not None
    assert (
        replace(removal(), reason="あ" * MAX_OPERATOR_FEEDBACK_TEXT).reason
        == "あ" * MAX_OPERATOR_FEEDBACK_TEXT
    )
    with pytest.raises(ValueError, match="bounded source fields"):
        replace(revision(), team_note="x" * (MAX_OPERATOR_FEEDBACK_TEXT + 1))
    with pytest.raises(ValueError, match="bounded source fields"):
        replace(revision(), descriptors=("x",) * 4)
    with pytest.raises(ValueError, match="bounded source fields"):
        replace(removal(), reason="x" * (MAX_OPERATOR_FEEDBACK_TEXT + 1))
    with pytest.raises(ValueError, match="recorded active"):
        replace(removal(), operator_access_active=False)
    with pytest.raises(ValueError, match="participants"):
        replace(root(), partner_id=uuid4())
    with pytest.raises(ValueError, match="timezone"):
        replace(revision(), changed_at=NOW.replace(tzinfo=None))
    with pytest.raises(ValueError, match="timezone"):
        OperatorFeedbackFilters(changed_from=NOW.replace(tzinfo=None))
    with pytest.raises(ValueError, match="half-open"):
        OperatorFeedbackFilters(changed_from=NOW, changed_before=NOW)
    with pytest.raises(ValueError, match="metadata anchor"):
        OperatorFeedbackTimePosition(NOW, UUID(int=1), NOW, UUID(int=2))
