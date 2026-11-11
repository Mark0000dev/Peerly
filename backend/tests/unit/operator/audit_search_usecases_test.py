"""Audit search security, returned-source scope and historical grant regression definitions."""

import asyncio
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest

from studymate.application.errors import StorageUnavailableError
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.operator.audit_search import SearchOperatorAudits
from studymate.application.operator.audit_search_ports import OperatorAuditFilters
from studymate.application.operator.authority import OperatorAccessDeniedError
from studymate.application.operator.cursors import InvalidOperatorCursorError
from studymate.domain.operator.audit import (
    OPERATOR_EVENT_PAGE_SIZE,
    OperatorAction,
    OperatorAudit,
    OperatorAuditOutcome,
    OperatorResourceKind,
)
from studymate.infrastructure.operator.audit_search_cursors import FernetOperatorAuditCursorCodec
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.unit.identity_store import CREDENTIAL, NOW
from tests.unit.operator.audit_search_store import (
    ACTION_ID,
    ORIGINAL_GRANT_VERSION,
    ORIGINAL_OPERATOR,
    REQUEST_ID,
    TARGET_ID,
    AuditSearchStore,
    original,
)

CODEC = FernetOperatorAuditCursorCodec.from_key(b"k" * 32)


def search(store: AuditSearchStore) -> SearchOperatorAudits:
    return SearchOperatorAudits(
        store, Sha256SessionHasher(), HmacIntentFingerprinter(b"h" * 32), CODEC
    )


async def test_page_audits_only_returned_originals_and_keyset_retains_original_grant() -> None:
    store = AuditSearchStore()
    store.assign_explicit_operator()
    store.rows = tuple(original(index) for index in range(OPERATOR_EVENT_PAGE_SIZE + 1, 0, -1))
    first = await search(store)(CREDENTIAL, OperatorAuditFilters())
    assert len(first.audits) == OPERATOR_EVENT_PAGE_SIZE
    assert first.next_cursor is not None
    assert first.search_anchor_at == NOW
    assert tuple(ref.id for ref in store.audit[0].results) == tuple(
        row.audit.id for row in first.audits
    )
    assert first.audits[0].audit.access.account_id == ORIGINAL_OPERATOR
    assert first.audits[0].audit.access.version == ORIGINAL_GRANT_VERSION
    # A newer source is excluded from this time-anchored continuation, not a commit snapshot.
    newer = original(OPERATOR_EVENT_PAGE_SIZE + 2)
    store.rows += (replace(newer, audit=replace(newer.audit, at=NOW + timedelta(seconds=1))),)
    second = await search(store)(CREDENTIAL, OperatorAuditFilters(), first.next_cursor)
    assert second.audits == (original(1),)
    assert second.next_cursor is None
    assert store.audit[-1].action == OperatorAction.SEARCH_AUDITS
    assert store.audit[-1].outcome == OperatorAuditOutcome.SEARCH


async def test_requested_target_filter_does_not_search_returned_resource_ids_or_family() -> None:
    store = AuditSearchStore()
    store.assign_explicit_operator()
    store.rows = (original(2, search=True), original(1))
    filters = OperatorAuditFilters(
        operator_id=ORIGINAL_OPERATOR,
        action=OperatorAction.READ_ACCOUNT,
        requested_kind=OperatorResourceKind.ACCOUNT,
        requested_id=TARGET_ID,
        http_request_id=REQUEST_ID,
        action_id=ACTION_ID,
        trace_id="a" * 32,
        occurred_from=NOW - timedelta(hours=1),
        occurred_before=NOW,
    )
    result = await search(store)(CREDENTIAL, filters)
    assert result.audits == (original(1),)
    assert (await search(store)(CREDENTIAL, replace(filters, requested_id=uuid4()))).audits == ()
    assert store.audit[-1].results == ()
    assert store.audit[-1].query_fingerprint is not None
    requested_only = await search(store)(
        CREDENTIAL, OperatorAuditFilters(requested_kind=OperatorResourceKind.ACCOUNT)
    )
    assert requested_only.audits == (original(1),)
    assert (
        await search(store)(CREDENTIAL, OperatorAuditFilters(action=OperatorAction.SEARCH_ACCOUNTS))
    ).audits == (original(2, search=True),)


async def test_current_grant_and_query_change_invalidate_cursor() -> None:
    store = AuditSearchStore()
    store.assign_explicit_operator()
    store.rows = tuple(original(index) for index in range(OPERATOR_EVENT_PAGE_SIZE + 1, 0, -1))
    first = await search(store)(CREDENTIAL, OperatorAuditFilters())
    assert first.next_cursor is not None
    with pytest.raises(InvalidOperatorCursorError):
        await search(store)(
            CREDENTIAL, OperatorAuditFilters(operator_id=uuid4()), first.next_cursor
        )
    assert store.access is not None
    store.access = replace(store.access, version=2)
    with pytest.raises(InvalidOperatorCursorError):
        await search(store)(CREDENTIAL, OperatorAuditFilters(), first.next_cursor)


@pytest.mark.parametrize("failure", ["role", "audit", "expiry", "revoked"])
async def test_no_result_without_current_authority_and_committed_audit(failure: str) -> None:
    store = AuditSearchStore()
    if failure != "role":
        store.assign_explicit_operator()
    if failure == "revoked":
        assert store.access is not None
        store.access = replace(store.access, active=False)
    store.rows = (original(1),)
    store.fail_audit = failure == "audit"
    store.expire_after_audit = failure == "expiry"
    error = (
        StorageUnavailableError
        if failure == "audit"
        else UnauthenticatedError
        if failure == "expiry"
        else OperatorAccessDeniedError
    )
    with pytest.raises(error):
        await search(store)(CREDENTIAL, OperatorAuditFilters())
    assert not store.audit
    if failure in ("role", "revoked"):
        assert store.private_queries == 0


@pytest.mark.parametrize("bad_source", ["oversize", "order", "duplicates", "anchor", "filter"])
async def test_out_of_scope_source_never_returns_or_audits_success(bad_source: str) -> None:
    store = AuditSearchStore()
    store.assign_explicit_operator()
    if bad_source == "oversize":
        rows = tuple(original(index) for index in range(OPERATOR_EVENT_PAGE_SIZE + 2, 0, -1))
    elif bad_source == "order":
        rows = (original(1), original(2))
    elif bad_source == "duplicates":
        rows = (original(1), original(1))
    elif bad_source == "anchor":
        row = original(1)
        rows = (replace(row, audit=replace(row.audit, at=NOW + timedelta(seconds=1))),)
    else:
        rows = (original(1),)
    store.forced_rows = rows
    filters = (
        OperatorAuditFilters(operator_id=uuid4())
        if bad_source == "filter"
        else OperatorAuditFilters()
    )
    with pytest.raises(RuntimeError):
        await search(store)(CREDENTIAL, filters)
    assert not store.audit


async def test_cancelled_audit_write_rolls_back_without_returning_private_metadata() -> None:
    class BlockedAuditStore(AuditSearchStore):
        def __init__(self) -> None:
            super().__init__()
            self.started = asyncio.Event()
            self.release = asyncio.Event()

        async def save_operator_audit(self, audit: OperatorAudit) -> None:
            await super().save_operator_audit(audit)
            self.started.set()
            await self.release.wait()

    store = BlockedAuditStore()
    store.assign_explicit_operator()
    store.rows = (original(1),)
    task = asyncio.create_task(search(store)(CREDENTIAL, OperatorAuditFilters()))
    await store.started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not store.audit
