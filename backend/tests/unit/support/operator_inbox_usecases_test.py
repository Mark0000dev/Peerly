import asyncio
from dataclasses import replace
from datetime import timedelta
from uuid import UUID, uuid4

import pytest

from studymate.application.errors import StorageUnavailableError
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.operator.authority import OperatorAccessDeniedError
from studymate.application.operator.cursors import InvalidOperatorCursorError
from studymate.application.support.operator_inbox import (
    ReadOperatorSupportHistory,
    SearchOperatorSupportCases,
)
from studymate.application.support.operator_inbox_ports import OperatorSupportFilters
from studymate.domain.operator.audit import OperatorAuditOutcome
from studymate.domain.support.cases import SupportReceipt, SupportStatus, SupportTopic
from studymate.domain.support.operator_inbox import (
    OPERATOR_SUPPORT_PAGE_SIZE,
    OperatorSupportRevision,
    OperatorSupportSummary,
)
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from studymate.infrastructure.support.operator_inbox_cursors import (
    FernetOperatorSupportInboxCursorCodec,
)
from tests.unit.identity_store import CREDENTIAL, NOW
from tests.unit.support.operator_inbox_store import (
    AuditCancellationStore,
    CommitFailureStore,
    InboxStore,
)

CODEC = FernetOperatorSupportInboxCursorCodec.from_key(b"k" * 32)


def search(store: InboxStore) -> SearchOperatorSupportCases:
    return SearchOperatorSupportCases(
        store, Sha256SessionHasher(), HmacIntentFingerprinter(b"h" * 32), CODEC
    )


def summary(index: int) -> OperatorSupportSummary:
    return OperatorSupportSummary(
        SupportReceipt(UUID(int=index + 1), SupportStatus.RECEIVED, 1, NOW, NOW),
        SupportTopic.CANNOT_SIGN_IN,
        None,
    )


async def test_inbox_lookahead_cursor_ties_filters_and_audited_empty_projection() -> None:
    store = InboxStore()
    store.assign_explicit_operator()
    store.cases = tuple(summary(index) for index in range(OPERATOR_SUPPORT_PAGE_SIZE + 1))
    first = await search(store)(CREDENTIAL, OperatorSupportFilters())
    assert len(first.cases) == OPERATOR_SUPPORT_PAGE_SIZE
    assert first.next_cursor is not None
    assert len(store.audit[0].results) == OPERATOR_SUPPORT_PAGE_SIZE
    assert store.audit[0].query_fingerprint is not None
    second = await search(store)(CREDENTIAL, OperatorSupportFilters(), first.next_cursor)
    assert second.cases == (summary(0),)
    assert second.next_cursor is None
    empty = await search(store)(CREDENTIAL, OperatorSupportFilters(actor_id=uuid4()))
    assert not empty.cases
    assert store.audit[-1].outcome == OperatorAuditOutcome.SEARCH
    assert store.audit[-1].results == ()
    with pytest.raises(InvalidOperatorCursorError):
        await search(store)(CREDENTIAL, OperatorSupportFilters(anonymous=True), first.next_cursor)


async def test_history_keeps_raw_versions_original_grants_and_cursor_anchor_after_append() -> None:
    store = InboxStore()
    store.assign_explicit_operator()
    case_id = uuid4()
    owner = store.actor.session.account_id
    rows = tuple(
        OperatorSupportRevision(
            SupportReceipt(
                case_id,
                SupportStatus.RECEIVED if version == 1 else SupportStatus.IN_REVIEW,
                version,
                NOW,
                NOW + timedelta(seconds=version),
            ),
            None if version == 1 else owner,
            None if version == 1 else 1,
        )
        for version in range(1, OPERATOR_SUPPORT_PAGE_SIZE + 2)
    )
    store.revisions[case_id] = rows
    history = ReadOperatorSupportHistory(store, Sha256SessionHasher(), CODEC)
    first = await history(CREDENTIAL, case_id)
    assert first is not None
    assert first.next_cursor is not None
    newer = replace(
        rows[-1], receipt=replace(rows[-1].receipt, version=rows[-1].receipt.version + 1)
    )
    store.revisions[case_id] = (*rows, newer)
    second = await history(CREDENTIAL, case_id, first.next_cursor)
    assert second is not None
    assert second.anchor_version == first.anchor_version
    assert second.revisions == (rows[0],)
    assert second.revisions[0].changed_by_id is None
    read_audit = store.audit[-1]
    assert read_audit.outcome == OperatorAuditOutcome.READ
    assert await history(CREDENTIAL, uuid4()) is None
    assert store.audit[-1].outcome == OperatorAuditOutcome.NOT_FOUND
    with pytest.raises(InvalidOperatorCursorError):
        await history(CREDENTIAL, uuid4(), first.next_cursor)


@pytest.mark.parametrize("failure", ["ordinary", "revoked", "banned", "expired"])
async def test_inbox_checks_actual_operator_before_sources(failure: str) -> None:
    store = InboxStore()
    if failure != "ordinary":
        store.assign_explicit_operator()
    if failure == "revoked":
        assert store.access is not None
        store.access = replace(store.access, active=False)
    elif failure == "banned":
        store.actor = replace(store.actor, banned=True)
    elif failure == "expired":
        store.clock = store.actor.session.expires_at
    expected = UnauthenticatedError if failure == "expired" else OperatorAccessDeniedError
    with pytest.raises(expected):
        await search(store)(CREDENTIAL, OperatorSupportFilters())
    assert store.private_queries == 0
    assert not store.audit


@pytest.mark.parametrize("history", [False, True])
@pytest.mark.parametrize("failure", ["audit", "final_session"])
async def test_audit_or_final_session_failure_prevents_return_and_rolls_back_audit(
    history: bool, failure: str
) -> None:
    store = InboxStore()
    store.assign_explicit_operator()
    store.fail_audit = failure == "audit"
    store.expire_after_audit = failure == "final_session"
    expected = StorageUnavailableError if failure == "audit" else UnauthenticatedError
    if history:
        with pytest.raises(expected):
            await ReadOperatorSupportHistory(store, Sha256SessionHasher(), CODEC)(
                CREDENTIAL, uuid4()
            )
    else:
        with pytest.raises(expected):
            await search(store)(CREDENTIAL, OperatorSupportFilters())
    assert not store.audit


@pytest.mark.parametrize("fault", ["too_many", "out_of_order", "wrong_filter", "future_source"])
async def test_inbox_rejects_broken_source_contract_before_auditing_or_returning(
    fault: str,
) -> None:
    store = InboxStore()
    store.assign_explicit_operator()
    row = summary(0)
    filters = OperatorSupportFilters()
    if fault == "too_many":
        store.forced_rows = tuple(summary(index) for index in range(OPERATOR_SUPPORT_PAGE_SIZE + 2))
    elif fault == "out_of_order":
        store.forced_rows = (row, summary(1))
    elif fault == "wrong_filter":
        store.forced_rows = (row,)
        filters = OperatorSupportFilters(actor_id=uuid4())
    else:
        store.forced_rows = (
            replace(
                row,
                receipt=replace(
                    row.receipt,
                    received_at=NOW + timedelta(seconds=1),
                    changed_at=NOW + timedelta(seconds=1),
                ),
            ),
        )
    with pytest.raises(RuntimeError, match=r"bounded|ordering|filters"):
        await search(store)(CREDENTIAL, filters)
    assert not store.audit


@pytest.mark.parametrize("history", [False, True])
async def test_cancellation_after_audit_starts_rolls_back_without_returning(history: bool) -> None:
    store = AuditCancellationStore()
    store.assign_explicit_operator()
    operation = (
        ReadOperatorSupportHistory(store, Sha256SessionHasher(), CODEC)(CREDENTIAL, uuid4())
        if history
        else search(store)(CREDENTIAL, OperatorSupportFilters())
    )
    task = asyncio.create_task(operation)
    try:
        await asyncio.wait_for(store.audit_started.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        store.audit_release.set()
        if not task.done():
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
    assert not store.audit


@pytest.mark.parametrize("history", [False, True])
async def test_transaction_commit_failure_prevents_prepared_result_from_escaping(
    history: bool,
) -> None:
    store = CommitFailureStore()
    store.assign_explicit_operator()
    operation = (
        ReadOperatorSupportHistory(store, Sha256SessionHasher(), CODEC)(CREDENTIAL, uuid4())
        if history
        else search(store)(CREDENTIAL, OperatorSupportFilters())
    )
    with pytest.raises(StorageUnavailableError):
        await operation
    assert not store.audit
