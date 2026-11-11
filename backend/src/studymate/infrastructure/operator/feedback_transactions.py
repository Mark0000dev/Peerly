"""Raw retained feedback sources, no current eligibility decoding or feedback mutations."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.elements import ColumnElement

from studymate.application.operator.feedback_ports import (
    OperatorFeedbackDirection,
    OperatorFeedbackFilters,
    OperatorFeedbackHistoryHead,
    OperatorFeedbackHistoryWindow,
    OperatorFeedbackTimePosition,
)
from studymate.domain.operator.peer_feedback import (
    OPERATOR_FEEDBACK_PAGE_SIZE,
    OperatorFeedbackRemoval,
    OperatorFeedbackRevision,
    OperatorFeedbackRoot,
)
from studymate.domain.operator.timeline import OperatorEventOrigin
from studymate.infrastructure.feedback.models import (
    PeerFeedbackRecord,
    PeerFeedbackRemovalRecord,
    PeerFeedbackRevisionRecord,
)
from studymate.infrastructure.operator.transactions import (
    OperatorAuditRecorder,
    SqlOperatorTransaction,
)
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.transactions import open_transaction


def feedback_participant(account_id: UUID) -> ColumnElement[bool]:
    return or_(
        PeerFeedbackRecord.reviewer_id == account_id, PeerFeedbackRecord.partner_id == account_id
    )


def root_value(row: PeerFeedbackRecord, changed_at: datetime) -> OperatorFeedbackRoot:
    return OperatorFeedbackRoot(
        row.id,
        row.reviewer_id,
        row.partner_id,
        row.conversation_id,
        row.low_id,
        row.high_id,
        row.current_version,
        row.current_removal_id,
        changed_at,
    )


def revision_value(row: PeerFeedbackRevisionRecord) -> OperatorFeedbackRevision:
    return OperatorFeedbackRevision(
        row.feedback_id,
        row.version,
        row.conversation_id,
        row.reviewer_id,
        row.partner_id,
        row.low_id,
        row.high_id,
        row.worked_confirmation_id,
        row.worked_answer,
        row.low_message_id,
        row.high_message_id,
        row.again,
        tuple(row.descriptors),
        row.team_note,
        row.changed_at,
        OperatorEventOrigin(row.http_request_id, row.action_id, row.trace_id, row.span_id),
    )


def removal_value(row: PeerFeedbackRemovalRecord) -> OperatorFeedbackRemoval:
    return OperatorFeedbackRemoval(
        row.id,
        row.feedback_id,
        row.source_version,
        row.operator_id,
        row.operator_access_version,
        row.operator_access_active,
        row.kind,
        row.reason,
        row.removed_at,
        OperatorEventOrigin(row.http_request_id, row.action_id, row.trace_id, row.span_id),
    )


@dataclass(frozen=True, slots=True)
class SqlOperatorFeedbackTransaction(SqlOperatorTransaction):
    async def feedback_account(self, account_id: UUID) -> UUID | None:
        self.checked_access()
        return await self.session.scalar(
            select(AccountRecord.id).where(AccountRecord.id == account_id)
        )

    async def feedback_roots(
        self,
        account_id: UUID,
        filters: OperatorFeedbackFilters,
        position: OperatorFeedbackTimePosition | None,
    ) -> tuple[OperatorFeedbackRoot, ...]:
        self.checked_access()
        statement = (
            select(PeerFeedbackRecord, PeerFeedbackRevisionRecord.changed_at)
            .join(
                PeerFeedbackRevisionRecord,
                (PeerFeedbackRevisionRecord.feedback_id == PeerFeedbackRecord.id)
                & (PeerFeedbackRevisionRecord.version == PeerFeedbackRecord.current_version),
            )
            .where(feedback_participant(account_id))
        )
        if filters.direction == OperatorFeedbackDirection.GIVEN:
            statement = statement.where(PeerFeedbackRecord.reviewer_id == account_id)
        elif filters.direction == OperatorFeedbackDirection.RECEIVED:
            statement = statement.where(PeerFeedbackRecord.partner_id == account_id)
        if filters.peer_id is not None:
            statement = statement.where(
                or_(
                    (PeerFeedbackRecord.reviewer_id == account_id)
                    & (PeerFeedbackRecord.partner_id == filters.peer_id),
                    (PeerFeedbackRecord.partner_id == account_id)
                    & (PeerFeedbackRecord.reviewer_id == filters.peer_id),
                )
            )
        if filters.removed is not None:
            statement = statement.where(
                PeerFeedbackRecord.current_removal_id.is_not(None)
                if filters.removed
                else PeerFeedbackRecord.current_removal_id.is_(None)
            )
        if filters.changed_from is not None:
            statement = statement.where(
                PeerFeedbackRevisionRecord.changed_at >= filters.changed_from
            )
        if filters.changed_before is not None:
            statement = statement.where(
                PeerFeedbackRevisionRecord.changed_at < filters.changed_before
            )
        if position is not None:
            key = tuple_(PeerFeedbackRevisionRecord.changed_at, PeerFeedbackRecord.id)
            statement = statement.where(
                key <= tuple_(position.anchor_at, position.anchor_id),
                key < tuple_(position.before_at, position.before_id),
            )
        rows = await self.session.execute(
            statement.order_by(
                PeerFeedbackRevisionRecord.changed_at.desc(), PeerFeedbackRecord.id.desc()
            ).limit(OPERATOR_FEEDBACK_PAGE_SIZE + 1)
        )
        return tuple(root_value(row, changed_at) for row, changed_at in rows)

    async def feedback_root(
        self, account_id: UUID, feedback_id: UUID
    ) -> OperatorFeedbackRoot | None:
        self.checked_access()
        row = (
            await self.session.execute(
                select(PeerFeedbackRecord, PeerFeedbackRevisionRecord.changed_at)
                .join(
                    PeerFeedbackRevisionRecord,
                    (PeerFeedbackRevisionRecord.feedback_id == PeerFeedbackRecord.id)
                    & (PeerFeedbackRevisionRecord.version == PeerFeedbackRecord.current_version),
                )
                .where(PeerFeedbackRecord.id == feedback_id, feedback_participant(account_id))
            )
        ).one_or_none()
        return root_value(row[0], row[1]) if row is not None else None

    async def feedback_history_head(
        self, account_id: UUID, feedback_id: UUID
    ) -> OperatorFeedbackHistoryHead | None:
        root = await self.feedback_root(account_id, feedback_id)
        if root is None:
            return None
        latest = await self.session.scalar(
            select(func.max(PeerFeedbackRevisionRecord.version)).where(
                PeerFeedbackRevisionRecord.feedback_id == feedback_id
            )
        )
        if latest is None:
            raise RuntimeError("Retained feedback lost its committed revision head")
        return OperatorFeedbackHistoryHead(root, latest)

    async def feedback_revisions(
        self, account_id: UUID, feedback_id: UUID, window: OperatorFeedbackHistoryWindow
    ) -> tuple[OperatorFeedbackRevision, ...]:
        self.checked_access()
        statement = (
            select(PeerFeedbackRevisionRecord)
            .join(
                PeerFeedbackRecord, PeerFeedbackRecord.id == PeerFeedbackRevisionRecord.feedback_id
            )
            .where(
                PeerFeedbackRecord.id == feedback_id,
                feedback_participant(account_id),
                PeerFeedbackRevisionRecord.version <= window.anchor_version,
            )
        )
        if window.before_version is not None:
            statement = statement.where(PeerFeedbackRevisionRecord.version < window.before_version)
        rows = await self.session.scalars(
            statement.order_by(PeerFeedbackRevisionRecord.version.desc()).limit(
                OPERATOR_FEEDBACK_PAGE_SIZE + 1
            )
        )
        return tuple(revision_value(row) for row in rows)

    async def feedback_removals(
        self, account_id: UUID, feedback_id: UUID, position: OperatorFeedbackTimePosition | None
    ) -> tuple[OperatorFeedbackRemoval, ...]:
        self.checked_access()
        statement = (
            select(PeerFeedbackRemovalRecord)
            .join(
                PeerFeedbackRecord, PeerFeedbackRecord.id == PeerFeedbackRemovalRecord.feedback_id
            )
            .where(PeerFeedbackRecord.id == feedback_id, feedback_participant(account_id))
        )
        if position is not None:
            key = tuple_(PeerFeedbackRemovalRecord.removed_at, PeerFeedbackRemovalRecord.id)
            statement = statement.where(
                key <= tuple_(position.anchor_at, position.anchor_id),
                key < tuple_(position.before_at, position.before_id),
            )
        rows = await self.session.scalars(
            statement.order_by(
                PeerFeedbackRemovalRecord.removed_at.desc(), PeerFeedbackRemovalRecord.id.desc()
            ).limit(OPERATOR_FEEDBACK_PAGE_SIZE + 1)
        )
        return tuple(removal_value(row) for row in rows)


@dataclass(frozen=True, slots=True)
class SqlOperatorFeedbackUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    recorder: OperatorAuditRecorder

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlOperatorFeedbackTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlOperatorFeedbackTransaction(session, self.recorder)
