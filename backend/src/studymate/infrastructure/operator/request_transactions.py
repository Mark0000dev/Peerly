"""Raw retained request reads; no student policy decoder, settlement, disclosure or ACK writes."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import load_only
from sqlalchemy.sql.elements import ColumnElement

from studymate.application.operator.request_ports import (
    OperatorRequestDirection,
    OperatorRequestFilters,
    OperatorRequestHistoryHead,
    OperatorRequestHistoryWindow,
    OperatorRequestPosition,
)
from studymate.domain.discovery import DiscoveryMode
from studymate.domain.operator.connection_requests import (
    OPERATOR_REQUEST_ACKS_PER_REVISION,
    OPERATOR_REQUEST_PAGE_SIZE,
    OperatorRequestAcknowledgement,
    OperatorRequestDisclosure,
    OperatorRequestOrigin,
    OperatorRequestPreview,
    OperatorRequestRevision,
    OperatorRequestRoot,
    OperatorRequestSnapshot,
)
from studymate.domain.requests.states import RequestState
from studymate.infrastructure.operator.transactions import (
    OperatorAuditRecorder,
    SqlOperatorTransaction,
)
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.transactions import open_transaction
from studymate.infrastructure.requests.models import (
    ConnectionRequestRecord,
    RequestPreviewRecord,
    RequestRevisionRecord,
)
from studymate.infrastructure.requests.view_models import (
    RequestDisclosureRecord,
    RequestViewAcknowledgementRecord,
)

ROOT_METADATA_COLUMNS = (
    ConnectionRequestRecord.id,
    ConnectionRequestRecord.relationship_id,
    ConnectionRequestRecord.sender_id,
    ConnectionRequestRecord.recipient_id,
    ConnectionRequestRecord.preview_id,
    ConnectionRequestRecord.current_version,
    ConnectionRequestRecord.state,
    ConnectionRequestRecord.sent_at,
    ConnectionRequestRecord.expires_at,
    ConnectionRequestRecord.request_id,
    ConnectionRequestRecord.action_id,
    ConnectionRequestRecord.trace_id,
    ConnectionRequestRecord.span_id,
)
PREVIEW_METADATA_COLUMNS = (
    RequestPreviewRecord.id,
    RequestPreviewRecord.mode,
    RequestPreviewRecord.subject_id,
)


def participant_scope(account_id: UUID) -> ColumnElement[bool]:
    return or_(
        ConnectionRequestRecord.sender_id == account_id,
        ConnectionRequestRecord.recipient_id == account_id,
    )


def root_value(row: ConnectionRequestRecord, preview: RequestPreviewRecord) -> OperatorRequestRoot:
    return OperatorRequestRoot(
        row.id,
        row.relationship_id,
        row.sender_id,
        row.recipient_id,
        row.preview_id,
        DiscoveryMode(preview.mode),
        preview.subject_id,
        row.sent_at,
        row.expires_at,
        row.current_version,
        RequestState(row.state),
        OperatorRequestOrigin(row.request_id, row.action_id, row.trace_id, row.span_id),
    )


def snapshot_value(
    row: ConnectionRequestRecord, preview: RequestPreviewRecord
) -> OperatorRequestSnapshot:
    return OperatorRequestSnapshot(
        root_value(row, preview),
        row.request_text,
        row.note,
        OperatorRequestPreview(
            preview.id,
            preview.sender_id,
            preview.recipient_id,
            DiscoveryMode(preview.mode),
            preview.subject_id,
            preview.created_at,
            preview.source_json,
            preview.sender_goal_id,
            preview.sender_goal_version,
            preview.recipient_goal_id,
            preview.recipient_goal_version,
            preview.sender_help_version,
            preview.recipient_help_version,
        ),
    )


def revision_value(row: RequestRevisionRecord) -> OperatorRequestRevision:
    return OperatorRequestRevision(
        row.request_id,
        row.version,
        RequestState(row.state),
        row.changed_at,
        row.decline_until,
        row.conversation_id,
    )


def ack_value(
    row: RequestViewAcknowledgementRecord, disclosure: RequestDisclosureRecord
) -> OperatorRequestAcknowledgement:
    return OperatorRequestAcknowledgement(
        row.id,
        row.viewer_id,
        row.request_id,
        row.stored_version,
        row.acknowledged_at,
        OperatorRequestOrigin(row.http_request_id, row.action_id, row.trace_id, row.span_id),
        OperatorRequestDisclosure(
            disclosure.id,
            disclosure.viewer_id,
            disclosure.request_id,
            disclosure.stored_version,
            disclosure.created_at,
            OperatorRequestOrigin(
                disclosure.http_request_id,
                disclosure.action_id,
                disclosure.trace_id,
                disclosure.span_id,
            ),
        ),
    )


@dataclass(frozen=True, slots=True)
class SqlOperatorRequestTransaction(SqlOperatorTransaction):
    async def request_account(self, account_id: UUID) -> UUID | None:
        self.checked_access()
        return await self.session.scalar(
            select(AccountRecord.id).where(AccountRecord.id == account_id)
        )

    async def request_roots(
        self,
        account_id: UUID,
        filters: OperatorRequestFilters,
        position: OperatorRequestPosition | None,
    ) -> tuple[OperatorRequestRoot, ...]:
        self.checked_access()
        statement = (
            select(ConnectionRequestRecord, RequestPreviewRecord)
            .options(
                load_only(*ROOT_METADATA_COLUMNS, raiseload=True),
                load_only(*PREVIEW_METADATA_COLUMNS, raiseload=True),
            )
            .join(
                RequestPreviewRecord, RequestPreviewRecord.id == ConnectionRequestRecord.preview_id
            )
            .where(participant_scope(account_id))
        )
        if filters.direction == OperatorRequestDirection.SENT:
            statement = statement.where(ConnectionRequestRecord.sender_id == account_id)
        elif filters.direction == OperatorRequestDirection.RECEIVED:
            statement = statement.where(ConnectionRequestRecord.recipient_id == account_id)
        if filters.peer_id is not None:
            statement = statement.where(
                or_(
                    (ConnectionRequestRecord.sender_id == account_id)
                    & (ConnectionRequestRecord.recipient_id == filters.peer_id),
                    (ConnectionRequestRecord.recipient_id == account_id)
                    & (ConnectionRequestRecord.sender_id == filters.peer_id),
                )
            )
        if filters.mode is not None:
            statement = statement.where(RequestPreviewRecord.mode == filters.mode.value)
        if filters.state is not None:
            statement = statement.where(ConnectionRequestRecord.state == filters.state.value)
        if filters.sent_from is not None:
            statement = statement.where(ConnectionRequestRecord.sent_at >= filters.sent_from)
        if filters.sent_before is not None:
            statement = statement.where(ConnectionRequestRecord.sent_at < filters.sent_before)
        if position is not None:
            statement = statement.where(
                tuple_(ConnectionRequestRecord.sent_at, ConnectionRequestRecord.id)
                <= tuple_(position.anchor_sent_at, position.anchor_request_id),
                tuple_(ConnectionRequestRecord.sent_at, ConnectionRequestRecord.id)
                < tuple_(position.before_sent_at, position.before_request_id),
            )
        rows = await self.session.execute(
            statement.order_by(
                ConnectionRequestRecord.sent_at.desc(), ConnectionRequestRecord.id.desc()
            ).limit(OPERATOR_REQUEST_PAGE_SIZE + 1)
        )
        return tuple(root_value(row, preview) for row, preview in rows)

    async def request_history_head(
        self, account_id: UUID, request_id: UUID
    ) -> OperatorRequestHistoryHead | None:
        self.checked_access()
        row = (
            await self.session.execute(
                select(ConnectionRequestRecord, RequestPreviewRecord)
                .options(
                    load_only(
                        *ROOT_METADATA_COLUMNS,
                        ConnectionRequestRecord.request_text,
                        ConnectionRequestRecord.note,
                        raiseload=True,
                    ),
                )
                .join(
                    RequestPreviewRecord,
                    RequestPreviewRecord.id == ConnectionRequestRecord.preview_id,
                )
                .where(
                    ConnectionRequestRecord.id == request_id,
                    participant_scope(account_id),
                )
            )
        ).one_or_none()
        if row is None:
            return None
        latest = await self.session.scalar(
            select(func.max(RequestRevisionRecord.version)).where(
                RequestRevisionRecord.request_id == request_id
            )
        )
        if latest is None:
            raise RuntimeError("Retained request lost its actual source revision head")
        return OperatorRequestHistoryHead(snapshot_value(row[0], row[1]), latest)

    async def request_revisions(
        self, account_id: UUID, request_id: UUID, window: OperatorRequestHistoryWindow
    ) -> tuple[OperatorRequestRevision, ...]:
        self.checked_access()
        statement = (
            select(RequestRevisionRecord)
            .join(
                ConnectionRequestRecord,
                ConnectionRequestRecord.id == RequestRevisionRecord.request_id,
            )
            .where(
                ConnectionRequestRecord.id == request_id,
                participant_scope(account_id),
                RequestRevisionRecord.version <= window.anchor_version,
            )
        )
        if window.before_version is not None:
            statement = statement.where(RequestRevisionRecord.version < window.before_version)
        rows = await self.session.scalars(
            statement.order_by(RequestRevisionRecord.version.desc()).limit(
                OPERATOR_REQUEST_PAGE_SIZE + 1
            )
        )
        return tuple(revision_value(row) for row in rows)

    async def request_page_acknowledgements(
        self, account_id: UUID, request_id: UUID, versions: tuple[int, ...]
    ) -> tuple[OperatorRequestAcknowledgement, ...]:
        self.checked_access()
        if not versions:
            return ()
        if len(versions) > OPERATOR_REQUEST_PAGE_SIZE:
            raise ValueError("Request ACK inspection exceeds its visible source revision page")
        rows = await self.session.execute(
            select(RequestViewAcknowledgementRecord, RequestDisclosureRecord)
            .join(
                RequestDisclosureRecord,
                (RequestDisclosureRecord.id == RequestViewAcknowledgementRecord.disclosure_id)
                & (RequestDisclosureRecord.viewer_id == RequestViewAcknowledgementRecord.viewer_id)
                & (
                    RequestDisclosureRecord.request_id
                    == RequestViewAcknowledgementRecord.request_id
                )
                & (
                    RequestDisclosureRecord.stored_version
                    == RequestViewAcknowledgementRecord.stored_version
                ),
            )
            .join(
                ConnectionRequestRecord,
                ConnectionRequestRecord.id == RequestViewAcknowledgementRecord.request_id,
            )
            .where(
                ConnectionRequestRecord.id == request_id,
                participant_scope(account_id),
                RequestViewAcknowledgementRecord.stored_version.in_(versions),
            )
            .order_by(
                RequestViewAcknowledgementRecord.stored_version.desc(),
                RequestViewAcknowledgementRecord.viewer_id,
            )
            .limit(OPERATOR_REQUEST_ACKS_PER_REVISION * len(versions) + 1)
        )
        return tuple(ack_value(ack, disclosure) for ack, disclosure in rows)


@dataclass(frozen=True, slots=True)
class SqlOperatorRequestUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    recorder: OperatorAuditRecorder

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlOperatorRequestTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlOperatorRequestTransaction(session, self.recorder)
