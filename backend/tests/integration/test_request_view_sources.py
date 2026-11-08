from uuid import UUID, uuid4

import pytest
from sqlalchemy import DateTime, cast, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from studymate.domain.requests.states import ConnectionRequest
from studymate.domain.requests.views import RequestViewReceipt
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import record_request_viewed
from studymate.infrastructure.requests.view_models import (
    RequestDisclosureRecord,
    RequestViewAcknowledgementRecord,
)
from tests.integration.migrations import run_revision_step
from tests.integration.requests.fixture import prepared, sent

pytestmark = pytest.mark.integration


async def receipt(
    session: AsyncSession, request: ConnectionRequest, viewer_id: UUID
) -> RequestViewReceipt:
    at = await session.scalar(select(cast(func.clock_timestamp(), DateTime(timezone=True))))
    assert at is not None
    disclosure = RequestDisclosureRecord(
        id=uuid4(),
        viewer_id=viewer_id,
        request_id=request.id,
        stored_version=request.version,
        sender_id=request.context.sender_id,
        recipient_id=request.context.recipient_id,
        created_at=at,
    )
    session.add(disclosure)
    await session.flush()
    result = RequestViewReceipt(uuid4(), viewer_id, request.id, request.version, disclosure.id, at)
    session.add(
        RequestViewAcknowledgementRecord(
            id=result.id,
            viewer_id=viewer_id,
            request_id=request.id,
            stored_version=request.version,
            disclosure_id=disclosure.id,
            acknowledged_at=at,
        )
    )
    await session.flush()
    return result


async def test_explicit_view_source_records_owned_canonical_event_without_private_content(
    identity_engine: AsyncEngine,
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    request = await sent(api, sender, recipient)
    async with api.sessions.begin() as session:
        viewed = await receipt(session, request, recipient.id)
        await record_request_viewed(session, viewed)
    async with api.sessions() as session:
        event = await session.scalar(
            select(ProductEventRecord).where(ProductEventRecord.request_view_ack_id == viewed.id)
        )
        assert event is not None
        assert event.account_id == recipient.id
        assert event.kind == "request.view_acknowledged"
        assert event.occurred_at == viewed.acknowledged_at
        assert event.connection_request_id is None
        assert event.request_initiator_id is None
        assert event.goal_id is None


@pytest.mark.parametrize("mismatch", ["viewer", "version", "mixed_event", "event_owner"])
async def test_owned_source_constraints_reject_cross_participant_version_and_event_shapes(
    identity_engine: AsyncEngine, mismatch: str
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    request = await sent(api, sender, recipient)
    async with api.sessions.begin() as session:
        viewed = await receipt(session, request, recipient.id)

    async def persist_invalid() -> None:
        async with api.sessions.begin() as session:
            if mismatch in ("viewer", "version"):
                session.add(
                    RequestViewAcknowledgementRecord(
                        id=uuid4(),
                        viewer_id=sender.id if mismatch == "viewer" else recipient.id,
                        request_id=request.id,
                        stored_version=request.version + 1
                        if mismatch == "version"
                        else request.version,
                        disclosure_id=viewed.disclosure_id,
                        acknowledged_at=viewed.acknowledged_at,
                    )
                )
            else:
                session.add(
                    ProductEventRecord(
                        id=uuid4(),
                        account_id=sender.id if mismatch == "event_owner" else recipient.id,
                        kind="request.view_acknowledged",
                        occurrence_key=str(uuid4()),
                        schema_version=1,
                        occurred_at=viewed.acknowledged_at,
                        request_view_ack_id=viewed.id,
                        connection_request_id=request.id if mismatch == "mixed_event" else None,
                    )
                )
            await session.flush()

    with pytest.raises(IntegrityError):
        await persist_invalid()


async def test_view_source_and_canonical_event_rollback_together(
    identity_engine: AsyncEngine,
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    request = await sent(api, sender, recipient)

    async def persist_then_fail() -> None:
        async with api.sessions.begin() as session:
            viewed = await receipt(session, request, recipient.id)
            await record_request_viewed(session, viewed)
            raise RuntimeError("Controlled post-event failure")

    with pytest.raises(RuntimeError, match="Controlled"):
        await persist_then_fail()
    async with api.sessions() as session:
        assert (
            await session.scalar(
                select(RequestDisclosureRecord.id).where(
                    RequestDisclosureRecord.request_id == request.id
                )
            )
            is None
        )
        assert (
            await session.scalar(
                select(RequestViewAcknowledgementRecord.id).where(
                    RequestViewAcknowledgementRecord.request_id == request.id
                )
            )
            is None
        )
        assert (
            await session.scalar(
                select(ProductEventRecord.id).where(
                    ProductEventRecord.kind == "request.view_acknowledged"
                )
            )
            is None
        )


async def test_downgrade_refuses_to_drop_real_disclosure_and_ack_history(
    identity_engine: AsyncEngine,
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    request = await sent(api, sender, recipient)
    async with api.sessions.begin() as session:
        viewed = await receipt(session, request, recipient.id)
        await record_request_viewed(session, viewed)

    with pytest.raises(RuntimeError, match="retained request disclosure"):
        async with identity_engine.begin() as connection:
            await connection.run_sync(run_revision_step, "0030_request_views", "downgrade")
    async with api.sessions() as session:
        assert await session.get(RequestViewAcknowledgementRecord, viewed.id) is not None
        assert await session.get(RequestDisclosureRecord, viewed.disclosure_id) is not None
