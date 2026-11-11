from datetime import UTC, datetime, timedelta, timezone
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from studymate.application.support.operator_inbox_ports import (
    OperatorSupportFilters,
    OperatorSupportHistoryPosition,
    OperatorSupportHistoryWindow,
    OperatorSupportPosition,
    OperatorSupportWindow,
)
from studymate.domain.operator.audit import OperatorAudit
from studymate.domain.support.cases import SupportReceipt, SupportStatus, SupportTopic
from studymate.domain.support.operator_inbox import OperatorSupportRevision, OperatorSupportSummary
from studymate.infrastructure.support.operator_inbox_transactions import (
    SqlOperatorSupportInboxTransaction,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable

NOW = datetime(2026, 11, 10, tzinfo=UTC)


def test_filter_fingerprint_preserves_anonymous_scope_and_normalizes_time_only() -> None:
    offset = NOW.astimezone(timezone(timedelta(hours=3)))
    assert OperatorSupportFilters(received_from=offset).fingerprint_parts() == (
        OperatorSupportFilters(received_from=NOW).fingerprint_parts()
    )
    assert len(
        {
            OperatorSupportFilters(anonymous=value).fingerprint_parts()
            for value in (None, True, False)
        }
    ) == len((None, True, False))
    actor = uuid4()
    assert str(actor) in OperatorSupportFilters(actor_id=actor).fingerprint_parts()
    with pytest.raises(ValueError, match="Anonymous"):
        OperatorSupportFilters(actor_id=actor, anonymous=True)


@pytest.mark.parametrize("before", [NOW, NOW - timedelta(seconds=1)])
def test_filters_reject_empty_or_reversed_time_interval(before: datetime) -> None:
    with pytest.raises(ValueError, match="half-open"):
        OperatorSupportFilters(received_from=NOW, received_before=before)


def test_received_anchor_rejects_future_position_and_naive_timestamps() -> None:
    with pytest.raises(ValueError, match="anchor"):
        OperatorSupportPosition(NOW, NOW + timedelta(seconds=1), uuid4())
    with pytest.raises(ValueError, match="timezone"):
        OperatorSupportFilters(received_from=NOW.replace(tzinfo=None))


@pytest.mark.parametrize(("anchor", "before"), [(0, 1), (1, 0), (1, 2), (True, 1), (1, True)])
def test_history_cursor_requires_bounded_source_versions(anchor: int, before: int) -> None:
    with pytest.raises(ValueError, match="positive versions"):
        OperatorSupportHistoryPosition(anchor, before)


def test_history_requires_actual_changed_by_grant_while_initial_receipt_is_unassigned() -> None:
    case_id, operator = uuid4(), uuid4()
    initial = SupportReceipt(case_id, SupportStatus.RECEIVED, 1, NOW, NOW)
    assert OperatorSupportRevision(initial, None, None).changed_by_id is None
    with pytest.raises(ValueError, match="invent"):
        OperatorSupportRevision(initial, operator, 1)
    changed = SupportReceipt(case_id, SupportStatus.IN_REVIEW, 2, NOW, NOW)
    revision = OperatorSupportRevision(changed, operator, 1)
    assert revision.changed_by_id == operator
    assert revision.operator_access_version == 1
    for actor, version in ((None, 1), (operator, None), (operator, 0), (operator, True)):
        with pytest.raises(ValueError, match="actual operator"):
            OperatorSupportRevision(changed, actor, version)


def test_inbox_summary_has_only_case_metadata_and_actual_optional_actor() -> None:
    receipt = SupportReceipt(uuid4(), SupportStatus.RECEIVED, 1, NOW, NOW)
    summary = OperatorSupportSummary(receipt, SupportTopic.CANNOT_SIGN_IN, None)
    assert summary.actor_id is None
    assert set(summary.__dataclass_fields__) == {"receipt", "topic", "actor_id"}


async def unexpected_audit(session: AsyncSession, audit: OperatorAudit) -> None:
    del session, audit
    raise AssertionError("Unguarded reads must stop before any audit or database operation")


@pytest.mark.parametrize("method", ["search", "history_head", "history"])
async def test_sql_support_reads_require_actual_operator_authority_before_database(
    method: str,
) -> None:
    # An unbound real session cannot execute SQL. Each method must reject at the
    # existing authority precondition rather than reaching a query or fabricating a grant.
    async with AsyncSession() as session:
        transaction = SqlOperatorSupportInboxTransaction(session, unexpected_audit)
        operation: Awaitable[object]
        if method == "search":
            operation = transaction.search_support_cases(
                OperatorSupportFilters(), OperatorSupportWindow(NOW, None)
            )
        elif method == "history_head":
            operation = transaction.support_history_head(uuid4())
        else:
            operation = transaction.support_history(uuid4(), OperatorSupportHistoryWindow(1, None))
        with pytest.raises(RuntimeError, match="actual current operator grant"):
            await operation
