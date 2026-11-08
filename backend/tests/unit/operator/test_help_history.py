from dataclasses import replace
from uuid import uuid4

import pytest

from studymate.application.errors import StorageUnavailableError
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.operator.authority import OperatorAccessDeniedError
from studymate.application.operator.cursors import InvalidOperatorCursorError, OperatorCursorScope
from studymate.application.operator.help_history import ReadOperatorHelpHistory
from studymate.application.operator.help_history_ports import (
    OperatorHelpHistoryHead,
    OperatorHelpHistoryPosition,
)
from studymate.domain.operator.audit import (
    OperatorAction,
    OperatorAuditOutcome,
    OperatorResourceKind,
    OperatorResourceRef,
)
from studymate.domain.operator.help_history import OPERATOR_HELP_HISTORY_PAGE_SIZE
from studymate.infrastructure.operator.cursors import encode_cursor
from studymate.infrastructure.operator.help_history_cursors import (
    FernetOperatorHelpHistoryCursorCodec,
)
from tests.unit.identity_store import CREDENTIAL, NOW
from tests.unit.operator.help_history_store import (
    CLEAR_VERSION,
    RAW_KEY,
    RAW_LABEL,
    RAW_NOTE,
    HelpHistoryStore,
    revision,
)
from tests.unit.operator.store import TARGET
from tests.unit.operator.test_authorized_reads import HASHER

CODEC = FernetOperatorHelpHistoryCursorCodec.from_key(b"h" * 32)


def read(store: HelpHistoryStore) -> ReadOperatorHelpHistory:
    return ReadOperatorHelpHistory(store, HASHER, CODEC)


async def test_raw_history_preserves_real_account_scope_and_clock_regression() -> None:
    store = HelpHistoryStore()
    store.assign_explicit_operator()
    store.actor = replace(
        store.actor, membership=None, activation_complete=False, registration=None
    )
    result = await read(store)(CREDENTIAL, TARGET)
    assert result is not None
    assert tuple(row.version for row in result.revisions) == (3, 2, 1)
    assert result.revisions[0].saved_at < result.revisions[-1].saved_at
    assert result.revisions[0].selections[0].subject_label == RAW_LABEL
    assert result.revisions[0].selections[0].topic_note == RAW_NOTE
    assert result.revisions[0].selections[0].topic_match_key == RAW_KEY
    assert tuple(selection.slot for selection in result.revisions[0].selections) == (1, 4)
    assert result.revisions[1].selections == ()
    audit = store.audit[-1]
    resource = OperatorResourceRef(OperatorResourceKind.ACCOUNT, TARGET)
    assert audit.action == OperatorAction.READ_ACCOUNT
    assert audit.requested == resource
    assert audit.results == (resource,)
    assert audit.outcome == OperatorAuditOutcome.READ
    assert RAW_NOTE not in repr(result)
    assert RAW_NOTE not in repr(audit)


async def test_existing_empty_account_reads_but_missing_account_commits_not_found() -> None:
    store = HelpHistoryStore()
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
    store = HelpHistoryStore()
    store.assign_explicit_operator()
    last_version = OPERATOR_HELP_HISTORY_PAGE_SIZE + 2
    store.histories[TARGET] = tuple(revision(number) for number in range(1, last_version + 1))
    first = await read(store)(CREDENTIAL, TARGET)
    assert first is not None
    assert len(first.revisions) == OPERATOR_HELP_HISTORY_PAGE_SIZE
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
    store = HelpHistoryStore()
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
    store = HelpHistoryStore()
    store.assign_explicit_operator()
    store.fail_audit = failure == "audit"
    store.expire_after_query = failure == "expiry_query"
    store.expire_after_audit = failure == "expiry_audit"
    with pytest.raises(StorageUnavailableError if failure == "audit" else UnauthenticatedError):
        await read(store)(CREDENTIAL, TARGET)
    assert not store.audit


@pytest.mark.parametrize("fault", ["owner", "duplicate", "ascending", "above_anchor", "excess"])
async def test_source_must_match_actual_target_and_bounded_descending_versions(fault: str) -> None:
    store = HelpHistoryStore()
    store.assign_explicit_operator()
    rows = {
        "owner": (revision(1, uuid4()),),
        "duplicate": (revision(2), revision(2)),
        "ascending": (revision(1), revision(2)),
        "above_anchor": (revision(4),),
        "excess": tuple(revision(1) for _ in range(OPERATOR_HELP_HISTORY_PAGE_SIZE + 2)),
    }
    store.rows_override = rows[fault]
    with pytest.raises(RuntimeError, match="Help history"):
        await read(store)(CREDENTIAL, TARGET)
    assert not store.audit


async def test_cross_account_head_and_future_cursor_are_never_source_authority() -> None:
    store = HelpHistoryStore()
    store.assign_explicit_operator()
    store.head_override = OperatorHelpHistoryHead(uuid4(), 3)
    with pytest.raises(RuntimeError, match="another actual account"):
        await read(store)(CREDENTIAL, TARGET)
    store.head_override = None
    scope = OperatorCursorScope(store.actor.session.account_id, 1)
    token = CODEC.encode_history(scope, TARGET, OperatorHelpHistoryPosition(4, 2))
    with pytest.raises(InvalidOperatorCursorError):
        await read(store)(CREDENTIAL, TARGET, token)
    assert not store.audit


@pytest.mark.parametrize("scope_change", ["actor", "grant", "target", "tampered", "oversized"])
def test_opaque_cursor_is_bound_to_actual_actor_role_target_and_version(scope_change: str) -> None:
    scope = OperatorCursorScope(uuid4(), 1)
    target = uuid4()
    position = OperatorHelpHistoryPosition(5, 2)
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
        ("operator-help-history-v1", str(scope.account_id), "1", str(target), anchor, before),
    )
    with pytest.raises(InvalidOperatorCursorError):
        CODEC.decode_history(scope, target, token)


def test_retained_labels_notes_and_keys_do_not_reapply_current_help_policy() -> None:
    original = revision(1)
    selected = original.selections[0]
    raw = replace(
        selected, subject_label=" ", topic_note="x" * 200, topic_match_key=" UNNORMALIZED ß "
    )
    retained = replace(original, selections=(raw,))
    assert retained.selections[0].subject_label == " "
    assert retained.selections[0].topic_note == "x" * 200
    assert retained.selections[0].topic_match_key == " UNNORMALIZED ß "
    with pytest.raises(ValueError, match="bounded nonnegative"):
        OperatorHelpHistoryHead(TARGET, -1)
    with pytest.raises(ValueError, match="bounded source versions"):
        OperatorHelpHistoryPosition(2, 3)
    with pytest.raises(ValueError, match="bounded positive"):
        replace(original, version=0)
    with pytest.raises(ValueError, match="nonnegative slot"):
        replace(selected, slot=-1)
    with pytest.raises(ValueError, match="32-byte"):
        FernetOperatorHelpHistoryCursorCodec.from_key(b"short")


@pytest.mark.parametrize("duplicate", [False, True])
async def test_actual_selection_order_is_part_of_the_retained_source(duplicate: bool) -> None:
    store = HelpHistoryStore()
    store.assign_explicit_operator()
    value = revision(1)
    selections = (
        value.selections[::-1] if not duplicate else (value.selections[0], value.selections[0])
    )
    store.rows_override = (replace(value, selections=selections),)
    with pytest.raises(RuntimeError, match="slot ordering"):
        await read(store)(CREDENTIAL, TARGET)
    assert not store.audit


async def test_saved_clear_is_not_lost_as_an_empty_history_collection() -> None:
    store = HelpHistoryStore()
    store.assign_explicit_operator()
    store.histories[TARGET] = (revision(2),)
    page = await read(store)(CREDENTIAL, TARGET)
    assert page is not None
    assert len(page.revisions) == 1
    assert page.revisions[0].version == CLEAR_VERSION
    assert page.revisions[0].selections == ()
    assert page.anchor_version == CLEAR_VERSION
    assert store.audit[-1].results == (OperatorResourceRef(OperatorResourceKind.ACCOUNT, TARGET),)


def test_profile_cursor_is_never_a_help_history_cursor_even_with_same_actor_key_and_versions() -> (
    None
):
    from studymate.application.operator.profile_history_ports import OperatorProfileHistoryPosition
    from studymate.infrastructure.operator.profile_history_cursors import (
        FernetOperatorProfileHistoryCursorCodec,
    )

    scope = OperatorCursorScope(uuid4(), 1)
    target = uuid4()
    profile = FernetOperatorProfileHistoryCursorCodec.from_key(b"h" * 32)
    token = profile.encode_history(scope, target, OperatorProfileHistoryPosition(5, 2))
    with pytest.raises(InvalidOperatorCursorError):
        CODEC.decode_history(scope, target, token)
