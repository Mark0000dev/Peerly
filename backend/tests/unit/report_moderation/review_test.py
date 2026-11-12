from dataclasses import replace
from uuid import uuid4

import pytest

from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.operator.authority import OperatorAccessDeniedError
from studymate.application.report_moderation.history import ReadReportReviewHistory
from studymate.application.report_moderation.review import (
    ReportReviewUnavailableError,
    ReportReviewVersionConflictError,
    ReviewReport,
    ReviewReportCommand,
)
from studymate.domain.operator.access import OperatorAccess
from studymate.domain.report_moderation.reviews import ReportReviewAction, ReportReviewReason
from studymate.infrastructure.report_moderation.cursors import FernetReportReviewHistoryCursorCodec
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from tests.unit.identity_store import CREDENTIAL, NOW
from tests.unit.operator.test_authorized_reads import HASHER
from tests.unit.report_moderation.store import REPORT_ID, ReviewStore

FINGERPRINTER = HmacIntentFingerprinter(b"r" * 32)
CODEC = FernetReportReviewHistoryCursorCodec.from_key(b"r" * 32)


def command() -> ReviewReportCommand:
    return ReviewReportCommand(
        CREDENTIAL,
        REPORT_ID,
        0,
        ReportReviewAction.DISMISS,
        ReportReviewReason("  documented private human reason  "),
        IntentKey("review-intent"),
    )


def reviewer(store: ReviewStore) -> ReviewReport:
    return ReviewReport(store, HASHER, FINGERPRINTER)


async def test_real_actor_proof_and_exact_replay_preserve_original_grant() -> None:
    store = ReviewStore()
    store.assign_explicit_operator()
    original = await reviewer(store)(command())
    store.access = OperatorAccess(original.operator.account_id, 2, True, NOW)
    assert await reviewer(store)(command()) == original
    assert original.operator.version == 1
    assert original.actor_session_id == store.actor.session.id
    assert original.reason == command().reason.value
    assert original.version == 1
    assert original.previous_version is None
    assert store.events == [original.event_id]
    assert not store.audit
    assert "documented private" not in repr(original)
    assert "documented private" not in repr(command())


async def test_conflicting_replay_and_stale_version_never_append() -> None:
    store = ReviewStore()
    store.assign_explicit_operator()
    first = await reviewer(store)(command())
    with pytest.raises(IdempotencyConflictError):
        await reviewer(store)(replace(command(), action=ReportReviewAction.ESCALATE))
    with pytest.raises(ReportReviewVersionConflictError):
        await reviewer(store)(replace(command(), intent_key=IntentKey("different-intent")))
    assert store.reviews == [first]
    next_ = await reviewer(store)(
        replace(
            command(),
            expected_version=1,
            action=ReportReviewAction.ESCALATE,
            intent_key=IntentKey("different-intent"),
        )
    )
    assert next_.version == first.version + 1
    assert next_.previous_version == 1


@pytest.mark.parametrize("state", ["absent", "revoked", "banned", "deleted", "expired"])
async def test_current_operator_authority_required_before_report_read(state: str) -> None:
    store = ReviewStore()
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
        await reviewer(store)(command())
    assert store.private_queries == 0
    assert not store.reviews
    assert not store.events


@pytest.mark.parametrize("failure", ["canonical", "commit", "expiry"])
async def test_any_atomic_failure_rolls_back_source_event_and_receipt(failure: str) -> None:
    store = ReviewStore()
    store.assign_explicit_operator()
    store.fail_event = failure == "canonical"
    store.fail_commit = failure == "commit"
    store.expire_after_write = failure == "expiry"
    with pytest.raises(UnauthenticatedError if failure == "expiry" else RuntimeError):
        await reviewer(store)(command())
    assert store.reviews == []
    assert store.events == []
    assert store.intents == {}


async def test_no_report_cannot_create_administrative_decision() -> None:
    store = ReviewStore()
    store.assign_explicit_operator()
    store.report = None
    with pytest.raises(ReportReviewUnavailableError):
        await reviewer(store)(command())
    assert not store.reviews
    assert not store.audit


async def test_unreviewed_is_empty_and_history_uses_real_read_audit() -> None:
    store = ReviewStore()
    store.assign_explicit_operator()
    read = ReadReportReviewHistory(store, HASHER, CODEC)
    empty = await read(CREDENTIAL, REPORT_ID)
    assert empty is not None
    assert empty.current is None
    assert empty.revisions == ()
    assert empty.anchor_version == 0
    original = await reviewer(store)(command())
    history = await read(CREDENTIAL, REPORT_ID)
    assert history is not None
    assert history.current == original
    assert history.revisions == (original,)
    assert store.audit[-1].action.value == "read_report"
    assert store.audit[-1].results[0].id == REPORT_ID
    assert await read(CREDENTIAL, uuid4()) is None
    assert store.audit[-1].outcome.value == "not_found"


@pytest.mark.parametrize("reason", ["", " \n ", "x" * 1001])
def test_every_human_decision_requires_bounded_nonblank_reason(reason: str) -> None:
    with pytest.raises(ValueError, match="documented reason"):
        ReportReviewReason(reason)


async def test_history_anchor_and_current_head_are_separate_truthful_views() -> None:
    from studymate.domain.report_moderation.reviews import REVIEW_HISTORY_PAGE_SIZE

    store = ReviewStore()
    store.assign_explicit_operator()
    write = reviewer(store)
    for version in range(REVIEW_HISTORY_PAGE_SIZE + 1):
        await write(
            replace(command(), expected_version=version, intent_key=IntentKey(str(uuid4())))
        )
    read = ReadReportReviewHistory(store, HASHER, CODEC)
    first = await read(CREDENTIAL, REPORT_ID)
    assert first is not None
    assert first.next_cursor is not None
    newest = await write(
        replace(
            command(),
            expected_version=REVIEW_HISTORY_PAGE_SIZE + 1,
            action=ReportReviewAction.ESCALATE,
            intent_key=IntentKey("newest-human-decision"),
        )
    )
    second = await read(CREDENTIAL, REPORT_ID, first.next_cursor)
    assert second is not None
    assert tuple(row.version for row in second.revisions) == (1,)
    assert second.anchor_version == first.anchor_version
    assert second.current == newest


@pytest.mark.parametrize("changed", ["actor", "grant", "report", "tamper"])
def test_history_cursor_never_grants_foreign_report_or_operator_access(changed: str) -> None:
    from studymate.application.operator.cursors import (
        InvalidOperatorCursorError,
        OperatorCursorScope,
    )
    from studymate.application.report_moderation.history import ReportReviewHistoryPosition

    scope = OperatorCursorScope(uuid4(), 1)
    report = REPORT_ID
    position = ReportReviewHistoryPosition(5, 2)
    token = CODEC.encode_history(scope, report, position)
    assert CODEC.decode_history(scope, report, token) == position
    if changed == "actor":
        scope = OperatorCursorScope(uuid4(), 1)
    elif changed == "grant":
        scope = OperatorCursorScope(scope.account_id, 2)
    elif changed == "report":
        report = uuid4()
    else:
        token = str(uuid4())
    with pytest.raises(InvalidOperatorCursorError):
        CODEC.decode_history(scope, report, token)


@pytest.mark.parametrize("failure", ["audit", "expiry"])
async def test_history_audit_failure_or_final_expiry_cannot_return_private_reason(
    failure: str,
) -> None:
    from studymate.application.errors import StorageUnavailableError

    store = ReviewStore()
    store.assign_explicit_operator()
    await reviewer(store)(command())
    store.fail_audit = failure == "audit"
    store.expire_after_audit = failure == "expiry"
    with pytest.raises(StorageUnavailableError if failure == "audit" else UnauthenticatedError):
        await ReadReportReviewHistory(store, HASHER, CODEC)(CREDENTIAL, REPORT_ID)
    assert not store.audit
    assert len(store.reviews) == 1
