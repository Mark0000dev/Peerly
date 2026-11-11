from dataclasses import replace
from datetime import timedelta
from uuid import UUID, uuid4

import pytest

from studymate.application.errors import StorageUnavailableError
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.operator.authority import OperatorAccessDeniedError
from studymate.application.operator.cursors import InvalidOperatorCursorError
from studymate.application.operator.profile_reports import (
    ReadOperatorProfileReport,
    SearchOperatorProfileReports,
)
from studymate.application.operator.report_ports import OperatorReportFilters
from studymate.domain.operator.audit import (
    OperatorAction,
    OperatorAuditOutcome,
    OperatorResourceKind,
    OperatorResourceRef,
)
from studymate.domain.operator.profile_reports import OPERATOR_REPORT_PAGE_SIZE
from studymate.infrastructure.operator.report_cursors import FernetOperatorReportCursorCodec
from tests.unit.identity_store import CREDENTIAL, NOW
from tests.unit.operator.report_store import ReportStore, report
from tests.unit.operator.test_authorized_reads import FINGERPRINTER, HASHER

CODEC = FernetOperatorReportCursorCodec.from_key(b"r" * 32)


def search(store: ReportStore) -> SearchOperatorProfileReports:
    return SearchOperatorProfileReports(store, HASHER, FINGERPRINTER, CODEC)


async def test_privileged_report_read_is_not_student_visibility_or_support_case_grant() -> None:
    store = ReportStore()
    store.assign_explicit_operator()
    store.actor = replace(
        store.actor, membership=None, activation_complete=False, registration=None
    )
    source = next(iter(store.details_by_report.values()))
    observed = await ReadOperatorProfileReport(store, HASHER)(CREDENTIAL, source.report.id)
    assert observed == source
    assert observed is not None
    assert observed.comment == " Exact private retained comment "
    inspection = store.audit[-1]
    assert inspection.action == OperatorAction.READ_REPORT
    assert inspection.results == (
        OperatorResourceRef(OperatorResourceKind.REPORT, source.report.id),
    )
    assert "private retained comment" not in repr(inspection)


async def test_missing_detail_commits_not_found_and_emptysearch_is_actual_search() -> None:
    store = ReportStore()
    store.assign_explicit_operator()
    assert await ReadOperatorProfileReport(store, HASHER)(CREDENTIAL, uuid4()) is None
    assert store.audit[-1].outcome == OperatorAuditOutcome.NOT_FOUND
    assert not store.audit[-1].results
    result = await search(store)(CREDENTIAL, OperatorReportFilters(target_id=uuid4()))
    assert result.reports == ()
    inspected = store.audit[-1]
    assert inspected.outcome == OperatorAuditOutcome.SEARCH
    assert inspected.query_fingerprint is not None


async def test_metadata50pagination_search_scope_and_private_comment_never_in_list() -> None:
    store = ReportStore()
    store.assign_explicit_operator()
    store.reports = tuple(
        report(report_id=UUID(int=index + 1)).report
        for index in range(OPERATOR_REPORT_PAGE_SIZE + 2)
    )
    first = await search(store)(CREDENTIAL, OperatorReportFilters())
    assert len(first.reports) == OPERATOR_REPORT_PAGE_SIZE
    assert first.next_cursor is not None
    assert len(store.audit[-1].results) == OPERATOR_REPORT_PAGE_SIZE
    assert all(not hasattr(item, "comment") for item in first.reports)
    second = await search(store)(CREDENTIAL, OperatorReportFilters(), first.next_cursor)
    assert {item.id for item in first.reports + second.reports} == {
        item.id for item in store.reports
    }
    assert second.next_cursor is None
    assert first.search_anchor_at == second.search_anchor_at
    with pytest.raises(InvalidOperatorCursorError):
        await search(store)(
            CREDENTIAL, OperatorReportFilters(reporter_id=uuid4()), first.next_cursor
        )


@pytest.mark.parametrize("fault", ["missing", "revoked", "banned", "deleted", "expired"])
async def test_new_report_reads_require_current_explicit_role_before_data(fault: str) -> None:
    store = ReportStore()
    if fault != "missing":
        store.assign_explicit_operator()
    if fault == "revoked":
        assert store.access is not None
        store.access = replace(store.access, active=False)
    elif fault == "banned":
        store.actor = replace(store.actor, banned=True)
    elif fault == "deleted":
        store.actor = replace(store.actor, deleted_at=NOW)
    elif fault == "expired":
        store.clock = store.actor.session.expires_at
    error = UnauthenticatedError if fault in {"deleted", "expired"} else OperatorAccessDeniedError
    with pytest.raises(error):
        await search(store)(CREDENTIAL, OperatorReportFilters())
    with pytest.raises(error):
        await ReadOperatorProfileReport(store, HASHER)(CREDENTIAL, uuid4())
    assert store.private_queries == 0
    assert not store.audit


@pytest.mark.parametrize("operation", ["search", "detail"])
@pytest.mark.parametrize("fault", ["storage", "final_expiry"])
async def test_mandatory_audit_and_final_guard_failures_return_no_private_data(
    operation: str, fault: str
) -> None:
    store = ReportStore()
    store.assign_explicit_operator()
    store.fail_audit = fault == "storage"
    store.expire_after_audit = fault == "final_expiry"
    error = StorageUnavailableError if fault == "storage" else UnauthenticatedError
    with pytest.raises(error):
        await read(store, operation)
    assert not store.audit


async def read(store: ReportStore, operation: str) -> None:
    if operation == "search":
        await search(store)(CREDENTIAL, OperatorReportFilters())
    else:
        await ReadOperatorProfileReport(store, HASHER)(
            CREDENTIAL, next(iter(store.details_by_report))
        )


@pytest.mark.parametrize("fault", ["unbounded", "order", "future", "wrong_detail"])
async def test_broken_source_projection_is_not_committed_as_false_audit(fault: str) -> None:
    store = ReportStore()
    store.assign_explicit_operator()
    missing = uuid4()
    if fault == "unbounded":
        store.report_rows = tuple(report().report for _ in range(OPERATOR_REPORT_PAGE_SIZE + 2))
    elif fault == "order":
        store.report_rows = (store.reports[0], store.reports[0])
    elif fault == "future":
        store.report_rows = (replace(store.reports[0], submitted_at=NOW + timedelta(seconds=1)),)
    else:
        store.details_by_report[missing] = next(iter(store.details_by_report.values()))
    with pytest.raises(RuntimeError, match=r"bounded|ordering|actual requested"):
        await broken_read(store, fault, missing)
    assert not store.audit


async def broken_read(store: ReportStore, fault: str, missing: UUID) -> None:
    if fault == "wrong_detail":
        await ReadOperatorProfileReport(store, HASHER)(CREDENTIAL, missing)
    else:
        await search(store)(CREDENTIAL, OperatorReportFilters())
