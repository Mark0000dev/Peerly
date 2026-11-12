from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID, uuid4

from studymate.application.identity.sessions import SessionCredential, SessionHasher
from studymate.application.operator.authority import finish_operator, require_operator
from studymate.application.operator.cursors import InvalidOperatorCursorError, OperatorCursorScope
from studymate.application.report_moderation.ports import ReportModerationUnitOfWork
from studymate.domain.operator.audit import (
    OperatorAction,
    OperatorAudit,
    OperatorAuditOutcome,
    OperatorResourceKind,
    OperatorResourceRef,
)
from studymate.domain.report_moderation.reviews import (
    MAX_REVIEW_VERSION,
    REVIEW_HISTORY_PAGE_SIZE,
    ReportReviewRevision,
    ReviewReportSource,
)


@dataclass(frozen=True, slots=True)
class ReportReviewHistoryPosition:
    anchor_version: int
    before_version: int

    def __post_init__(self) -> None:
        if (
            any(
                isinstance(value, bool) or not 1 <= value <= MAX_REVIEW_VERSION
                for value in (self.anchor_version, self.before_version)
            )
            or self.before_version > self.anchor_version
        ):
            raise ValueError("Report review cursor requires bounded actual source versions")


class ReportReviewHistoryCursorCodec(Protocol):
    def encode_history(
        self, scope: OperatorCursorScope, target_id: UUID, position: ReportReviewHistoryPosition
    ) -> str: ...
    def decode_history(
        self, scope: OperatorCursorScope, target_id: UUID, token: str
    ) -> ReportReviewHistoryPosition: ...


@dataclass(frozen=True, slots=True)
class ReportReviewHistoryPage:
    report: ReviewReportSource
    current: ReportReviewRevision | None = field(repr=False)
    revisions: tuple[ReportReviewRevision, ...] = field(repr=False)
    anchor_version: int
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class ReadReportReviewHistory:
    unit_of_work: ReportModerationUnitOfWork
    hasher: SessionHasher
    cursor_codec: ReportReviewHistoryCursorCodec

    async def __call__(
        self, credential: SessionCredential, report_id: UUID, cursor: str | None = None
    ) -> ReportReviewHistoryPage | None:
        digest = await self.hasher.digest(credential)
        async with self.unit_of_work.transaction(digest, report_id) as transaction:
            principal = await require_operator(transaction, credential, self.hasher)
            report = await transaction.lock_report(report_id)
            result = None
            if report is not None:
                if report.id != report_id:
                    raise RuntimeError("Report review history belongs to another report")
                latest = await transaction.latest_review(report_id)
                if latest is not None and latest.report_id != report_id:
                    raise RuntimeError("Report review head belongs to another report")
                latest_version = latest.version if latest is not None else 0
                scope = OperatorCursorScope(principal.access.account_id, principal.access.version)
                position = (
                    self.cursor_codec.decode_history(scope, report_id, cursor)
                    if cursor is not None
                    else None
                )
                if position is not None and position.anchor_version > latest_version:
                    raise InvalidOperatorCursorError
                anchor = position.anchor_version if position is not None else latest_version
                before = position.before_version if position is not None else None
                rows = await transaction.review_history(report_id, anchor, before)
                previous = before if before is not None else anchor + 1
                if len(rows) > REVIEW_HISTORY_PAGE_SIZE + 1:
                    raise RuntimeError("Report review history exceeded its bounded page")
                for row in rows:
                    if (
                        row.report_id != report_id
                        or row.version > anchor
                        or row.version >= previous
                    ):
                        raise RuntimeError(
                            "Report review history violates actual source ownership/order"
                        )
                    previous = row.version
                visible = rows[:REVIEW_HISTORY_PAGE_SIZE]
                next_cursor = (
                    self.cursor_codec.encode_history(
                        scope, report_id, ReportReviewHistoryPosition(anchor, visible[-1].version)
                    )
                    if len(rows) > REVIEW_HISTORY_PAGE_SIZE
                    else None
                )
                result = ReportReviewHistoryPage(report, latest, visible, anchor, next_cursor)
            reference = OperatorResourceRef(OperatorResourceKind.REPORT, report_id)
            await transaction.save_operator_audit(
                OperatorAudit(
                    uuid4(),
                    principal.access,
                    OperatorAction.READ_REPORT,
                    reference,
                    (reference,) if report is not None else (),
                    await transaction.now(),
                    OperatorAuditOutcome.READ
                    if report is not None
                    else OperatorAuditOutcome.NOT_FOUND,
                )
            )
            await finish_operator(transaction, principal)
            return result
