"""Actual0055 trigger/lease definitions, run only in coordinated migrated-schema batch."""

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.external_delivery.routing import MaterializeDeliverySources
from studymate.domain.external_delivery.delivery import DeliveryResult, DestinationRef, ResultKind
from studymate.domain.external_delivery.sources import Sink
from studymate.infrastructure.external_delivery.destinations import (
    DestinationRegistration,
    register_destinations,
)
from studymate.infrastructure.external_delivery.materialization import (
    SqlMaterializationUnitOfWork,
    database_now,
)
from studymate.infrastructure.external_delivery.models import (
    DeliveryAttemptRecord,
    DeliverySourceRecord,
    ExternalDeliveryRecord,
)
from studymate.infrastructure.external_delivery.queue import SqlExternalDeliveryQueue
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from tests.integration.student_actor import actor

pytestmark = pytest.mark.integration


async def test_legacy_direct_writer_capture_rolls_back_and_late_commit_is_not_lost(
    identity_engine: AsyncEngine,
) -> None:
    owner = await actor(identity_engine)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    async with sessions() as first, sessions() as second:
        async with first.begin():
            older = ProductEventRecord(
                id=uuid4(),
                account_id=owner.id,
                kind="auth.email_confirmed",
                occurrence_key="institutional_binding",
                schema_version=1,
                occurred_at=await database_now(first),
            )
            first.add(older)
            await first.flush()
            # A later-captured row commits first; no monotonic timestamp cursor may hide older.
            async with second.begin():
                newer = ProductEventRecord(
                    id=uuid4(),
                    account_id=owner.id,
                    kind="auth.email_confirmed",
                    occurrence_key=f"smv1:{uuid4().hex}:p:operator",
                    schema_version=1,
                    occurred_at=await database_now(second),
                )
                second.add(newer)
            materialize = MaterializeDeliverySources(SqlMaterializationUnitOfWork(sessions))
            assert await materialize() == 1
        assert await materialize() == 1
        async with first.begin():
            sources = tuple(await first.scalars(select(DeliverySourceRecord)))
            assert {source.canonical_event_id for source in sources} == {older.id, newer.id}
            assert all(source.materialized_at is not None for source in sources)
        rolled_back = uuid4()

        async def rollback_source() -> None:
            async with first.begin():
                first.add(
                    ProductEventRecord(
                        id=rolled_back,
                        account_id=owner.id,
                        kind="auth.email_confirmed",
                        occurrence_key=f"smv1:{uuid4().hex}:p:operator",
                        schema_version=1,
                        occurred_at=await database_now(first),
                    )
                )
                await first.flush()
                raise RuntimeError("rollback")

        with pytest.raises(RuntimeError, match="rollback"):
            await rollback_source()
        assert (
            await first.scalar(
                select(DeliverySourceRecord.id).where(
                    DeliverySourceRecord.canonical_event_id == rolled_back
                )
            )
            is None
        )


async def test_unregistered_destination_no_attempt_and_stale_ack_preserves_new_lease(
    identity_engine: AsyncEngine,
) -> None:
    owner = await actor(identity_engine)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    async with sessions.begin() as session:
        event = ProductEventRecord(
            id=uuid4(),
            account_id=owner.id,
            kind="auth.email_confirmed",
            occurrence_key="institutional_binding",
            schema_version=1,
            occurred_at=await database_now(session),
        )
        session.add(event)
    assert await MaterializeDeliverySources(SqlMaterializationUnitOfWork(sessions))() == 1
    queue = SqlExternalDeliveryQueue(sessions)
    destination = DestinationRef(Sink.UMAMI, 1)
    assert await queue.claim(destination, 30) is None
    async with sessions() as session:
        delivery = (await session.scalars(select(ExternalDeliveryRecord))).one()
        assert delivery.attempt_count == 0
        assert delivery.destination_revision is None
    await register_destinations(sessions, (DestinationRegistration(destination, b"a" * 32),))
    old = await queue.claim(destination, 30)
    assert old is not None
    assert await queue.claim(destination, 30) is None
    async with sessions.begin() as session:
        await session.execute(
            update(ExternalDeliveryRecord)
            .where(ExternalDeliveryRecord.id == old.delivery_id)
            .values(lease_until=func.clock_timestamp() - timedelta(seconds=1))
        )
    # Expiry closes the old attempt ambiguously and schedules a bounded retry.
    assert await queue.claim(destination, 30) is None
    async with sessions.begin() as session:
        await session.execute(
            update(ExternalDeliveryRecord)
            .where(ExternalDeliveryRecord.id == old.delivery_id)
            .values(next_attempt_at=func.clock_timestamp() - timedelta(seconds=1))
        )
    current = await queue.claim(destination, 30)
    assert current is not None
    await queue.finish(old, DeliveryResult(ResultKind.ACCEPTED, http_status=200))
    async with sessions() as session:
        actual = await session.get(ExternalDeliveryRecord, old.delivery_id)
        first = await session.get(DeliveryAttemptRecord, (old.delivery_id, 1))
        assert actual is not None
        assert first is not None
        assert actual.lease_id == current.lease_id
        assert actual.state == "leased"
        assert actual.delivered_at is None
        assert first.outcome == "lease_expired"
        assert first.late_ack_at is not None
    await queue.finish(current, DeliveryResult(ResultKind.ACCEPTED, http_status=200))
    assert await queue.claim(DestinationRef(Sink.UMAMI, 2), 30) is None
    with pytest.raises(ValueError, match="cannot change"):
        await register_destinations(sessions, (DestinationRegistration(destination, b"b" * 32),))
