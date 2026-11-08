from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.idempotency import IntentKey
from studymate.application.requests.viewing import RequestViewIntent
from studymate.domain.requests.states import RequestUnavailableError
from studymate.domain.requests.views import RequestDisclosure, RequestViewReceipt
from studymate.infrastructure.observability.tracing import current_origin
from studymate.infrastructure.persistence.transactions import open_transaction
from studymate.infrastructure.requests.codec import StoredRequestSnapshotError
from studymate.infrastructure.requests.models import (
    ConnectionRequestRecord,
    RequestCommandIntentRecord,
    RequestRevisionRecord,
)
from studymate.infrastructure.requests.queries import SqlRequestQueryTransaction
from studymate.infrastructure.requests.view_models import (
    RequestDisclosureRecord,
    RequestViewAcknowledgementRecord,
)


class RequestViewedRecorder(Protocol):
    async def __call__(self, session: AsyncSession, receipt: RequestViewReceipt) -> None: ...


def view_receipt(record: RequestViewAcknowledgementRecord) -> RequestViewReceipt:
    return RequestViewReceipt(
        record.id,
        record.viewer_id,
        record.request_id,
        record.stored_version,
        record.disclosure_id,
        record.acknowledged_at,
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class SqlRequestViewTransaction(SqlRequestQueryTransaction):
    recorder: RequestViewedRecorder

    async def disclosure(
        self, viewer_id: UUID, request_id: UUID, disclosure_id: UUID
    ) -> RequestDisclosure | None:
        self.check_actor(viewer_id)
        record = await self.session.scalar(
            select(RequestDisclosureRecord).where(
                RequestDisclosureRecord.id == disclosure_id,
                RequestDisclosureRecord.viewer_id == viewer_id,
                RequestDisclosureRecord.request_id == request_id,
            )
        )
        return (
            RequestDisclosure(
                record.id,
                record.viewer_id,
                record.request_id,
                record.stored_version,
                record.created_at,
            )
            if record is not None
            else None
        )

    async def view_intent(self, actor_id: UUID, key: IntentKey) -> RequestViewIntent | None:
        self.check_actor(actor_id)
        record = await self.session.get(RequestCommandIntentRecord, (actor_id, "viewed", key.value))
        if record is None:
            return None
        receipt = await self.session.scalar(
            select(RequestViewAcknowledgementRecord).where(
                RequestViewAcknowledgementRecord.id == record.result_view_ack_id,
                RequestViewAcknowledgementRecord.viewer_id == actor_id,
            )
        )
        if record.result_kind != "viewed" or receipt is None:
            raise StoredRequestSnapshotError("Stored request view intent lacks its owned receipt")
        return RequestViewIntent(record.fingerprint, view_receipt(receipt))

    async def acknowledge(self, source: RequestViewReceipt) -> RequestViewReceipt:
        self.check_actor(source.viewer_id)
        origin = current_origin()
        inserted = await self.session.scalar(
            insert(RequestViewAcknowledgementRecord)
            .values(
                id=source.id,
                viewer_id=source.viewer_id,
                request_id=source.request_id,
                stored_version=source.stored_version,
                disclosure_id=source.disclosure_id,
                acknowledged_at=source.acknowledged_at,
                http_request_id=origin.request_id if origin is not None else None,
                action_id=origin.action_id if origin is not None else None,
                trace_id=origin.trace_id if origin is not None else None,
                span_id=origin.span_id if origin is not None else None,
            )
            .on_conflict_do_nothing(constraint="uq_request_view_ack_source")
            .returning(RequestViewAcknowledgementRecord.id)
        )
        if inserted is not None:
            await self.recorder(self.session, source)
            return source
        original = (
            await self.session.scalars(
                select(RequestViewAcknowledgementRecord).where(
                    RequestViewAcknowledgementRecord.viewer_id == source.viewer_id,
                    RequestViewAcknowledgementRecord.request_id == source.request_id,
                    RequestViewAcknowledgementRecord.stored_version == source.stored_version,
                )
            )
        ).one()
        return view_receipt(original)

    async def remember_view(
        self, actor_id: UUID, key: IntentKey, intent: RequestViewIntent, at: datetime
    ) -> None:
        self.check_actor(actor_id)
        receipt = intent.receipt
        row = (
            await self.session.execute(
                select(ConnectionRequestRecord, RequestRevisionRecord)
                .join(
                    RequestRevisionRecord,
                    RequestRevisionRecord.request_id == ConnectionRequestRecord.id,
                )
                .where(
                    ConnectionRequestRecord.id == receipt.request_id,
                    or_(
                        ConnectionRequestRecord.sender_id == actor_id,
                        ConnectionRequestRecord.recipient_id == actor_id,
                    ),
                    RequestRevisionRecord.version == receipt.stored_version,
                )
            )
        ).one_or_none()
        if row is None or actor_id not in (row[0].sender_id, row[0].recipient_id):
            raise RequestUnavailableError
        request, revision = row
        origin = current_origin()
        self.session.add(
            RequestCommandIntentRecord(
                actor_id=actor_id,
                operation="viewed",
                key=key.value,
                peer_id=request.recipient_id
                if request.sender_id == actor_id
                else request.sender_id,
                fingerprint=intent.fingerprint,
                created_at=at,
                result_kind="viewed",
                result_view_ack_id=receipt.id,
                result_request_id=receipt.request_id,
                result_request_version=receipt.stored_version,
                result_request_state=revision.state,
                result_sender_id=request.sender_id,
                result_recipient_id=request.recipient_id,
                request_id=origin.request_id if origin is not None else None,
                action_id=origin.action_id if origin is not None else None,
                trace_id=origin.trace_id if origin is not None else None,
                span_id=origin.span_id if origin is not None else None,
            )
        )
        await self.session.flush()


@dataclass(frozen=True, slots=True)
class SqlRequestViewUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    recorder: RequestViewedRecorder

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlRequestViewTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlRequestViewTransaction(session, recorder=self.recorder)
