"""All retained technical disclosures, exact linked ACKs; no participant-read side effects."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import load_only

from studymate.application.operator.disclosure_ports import (
    OperatorDisclosureFilters,
    OperatorDisclosurePosition,
)
from studymate.domain.operator.connection_requests import (
    OperatorRequestAcknowledgement,
    OperatorRequestOrigin,
    OperatorRequestRoot,
)
from studymate.domain.operator.request_disclosures import (
    OPERATOR_DISCLOSURE_PAGE_SIZE,
    OperatorRetainedDisclosure,
)
from studymate.infrastructure.operator.request_transactions import (
    PREVIEW_METADATA_COLUMNS,
    ROOT_METADATA_COLUMNS,
    ack_value,
    participant_scope,
    root_value,
)
from studymate.infrastructure.operator.transactions import (
    OperatorAuditRecorder,
    SqlOperatorTransaction,
)
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.transactions import open_transaction
from studymate.infrastructure.requests.models import ConnectionRequestRecord, RequestPreviewRecord
from studymate.infrastructure.requests.view_models import (
    RequestDisclosureRecord,
    RequestViewAcknowledgementRecord,
)


def disclosure_value(row: RequestDisclosureRecord) -> OperatorRetainedDisclosure:
    return OperatorRetainedDisclosure(
        row.id,
        row.viewer_id,
        row.request_id,
        row.stored_version,
        row.sender_id,
        row.recipient_id,
        row.created_at,
        OperatorRequestOrigin(row.http_request_id, row.action_id, row.trace_id, row.span_id),
    )


@dataclass(frozen=True, slots=True)
class SqlOperatorDisclosureTransaction(SqlOperatorTransaction):
    async def disclosure_account(self, account_id: UUID) -> UUID | None:
        self.checked_access()
        return await self.session.scalar(
            select(AccountRecord.id).where(AccountRecord.id == account_id)
        )

    async def disclosure_request(
        self,
        account_id: UUID,
        request_id: UUID,
    ) -> OperatorRequestRoot | None:
        self.checked_access()
        row = (
            await self.session.execute(
                select(ConnectionRequestRecord, RequestPreviewRecord)
                .options(
                    load_only(*ROOT_METADATA_COLUMNS, raiseload=True),
                    load_only(*PREVIEW_METADATA_COLUMNS, raiseload=True),
                )
                .join(
                    RequestPreviewRecord,
                    RequestPreviewRecord.id == ConnectionRequestRecord.preview_id,
                )
                .where(ConnectionRequestRecord.id == request_id, participant_scope(account_id))
            )
        ).one_or_none()
        return root_value(row[0], row[1]) if row is not None else None

    async def request_disclosures(
        self,
        account_id: UUID,
        request_id: UUID,
        filters: OperatorDisclosureFilters,
        position: OperatorDisclosurePosition | None,
    ) -> tuple[OperatorRetainedDisclosure, ...]:
        self.checked_access()
        statement = (
            select(RequestDisclosureRecord)
            .join(
                ConnectionRequestRecord,
                ConnectionRequestRecord.id == RequestDisclosureRecord.request_id,
            )
            .where(ConnectionRequestRecord.id == request_id, participant_scope(account_id))
        )
        if filters.viewer_id is not None:
            statement = statement.where(RequestDisclosureRecord.viewer_id == filters.viewer_id)
        if filters.stored_version is not None:
            statement = statement.where(
                RequestDisclosureRecord.stored_version == filters.stored_version
            )
        if filters.disclosure_id is not None:
            statement = statement.where(RequestDisclosureRecord.id == filters.disclosure_id)
        if filters.acknowledgement_id is not None:
            statement = statement.where(
                select(RequestViewAcknowledgementRecord.id)
                .where(
                    RequestViewAcknowledgementRecord.id == filters.acknowledgement_id,
                    RequestViewAcknowledgementRecord.disclosure_id == RequestDisclosureRecord.id,
                    RequestViewAcknowledgementRecord.viewer_id == RequestDisclosureRecord.viewer_id,
                    RequestViewAcknowledgementRecord.request_id
                    == RequestDisclosureRecord.request_id,
                    RequestViewAcknowledgementRecord.stored_version
                    == RequestDisclosureRecord.stored_version,
                )
                .exists()
            )
        if filters.created_from is not None:
            statement = statement.where(RequestDisclosureRecord.created_at >= filters.created_from)
        if filters.created_before is not None:
            statement = statement.where(RequestDisclosureRecord.created_at < filters.created_before)
        if position is not None:
            key = tuple_(RequestDisclosureRecord.created_at, RequestDisclosureRecord.id)
            statement = statement.where(
                key <= tuple_(position.anchor_created_at, position.anchor_disclosure_id),
                key < tuple_(position.before_created_at, position.before_disclosure_id),
            )
        rows = await self.session.scalars(
            statement.order_by(
                RequestDisclosureRecord.created_at.desc(), RequestDisclosureRecord.id.desc()
            ).limit(OPERATOR_DISCLOSURE_PAGE_SIZE + 1)
        )
        return tuple(disclosure_value(row) for row in rows)

    async def disclosure_page_acknowledgements(
        self,
        account_id: UUID,
        request_id: UUID,
        disclosure_ids: tuple[UUID, ...],
    ) -> tuple[OperatorRequestAcknowledgement, ...]:
        self.checked_access()
        if len(disclosure_ids) > OPERATOR_DISCLOSURE_PAGE_SIZE:
            raise ValueError("Disclosure ACK inspection exceeds its actual visible page")
        if not disclosure_ids:
            return ()
        rows = await self.session.execute(
            select(RequestViewAcknowledgementRecord, RequestDisclosureRecord)
            .join(
                RequestDisclosureRecord,
                (
                    (RequestDisclosureRecord.id == RequestViewAcknowledgementRecord.disclosure_id)
                    & (
                        RequestDisclosureRecord.viewer_id
                        == RequestViewAcknowledgementRecord.viewer_id
                    )
                    & (
                        RequestDisclosureRecord.request_id
                        == RequestViewAcknowledgementRecord.request_id
                    )
                    & (
                        RequestDisclosureRecord.stored_version
                        == RequestViewAcknowledgementRecord.stored_version
                    )
                ),
            )
            .join(
                ConnectionRequestRecord,
                ConnectionRequestRecord.id == RequestDisclosureRecord.request_id,
            )
            .where(
                ConnectionRequestRecord.id == request_id,
                participant_scope(account_id),
                RequestDisclosureRecord.id.in_(disclosure_ids),
            )
            .order_by(RequestViewAcknowledgementRecord.id)
            .limit(len(disclosure_ids) + 1)
        )
        return tuple(ack_value(ack, disclosure) for ack, disclosure in rows)


@dataclass(frozen=True, slots=True)
class SqlOperatorDisclosureUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    recorder: OperatorAuditRecorder

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlOperatorDisclosureTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlOperatorDisclosureTransaction(session, self.recorder)
