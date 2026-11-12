"""Real54→55 history: no default replay; explicit canonical seeding is Umami-only."""

from uuid import uuid4

import pytest
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.external_delivery.maintenance import SeedUmamiBackfill
from studymate.application.external_delivery.routing import MaterializeDeliverySources
from studymate.domain.external_delivery.sources import CanonicalSource, MembershipEvidence
from studymate.infrastructure.external_delivery.maintenance import SqlMaintenanceUnitOfWork
from studymate.infrastructure.external_delivery.materialization import (
    SqlMaterializationUnitOfWork,
    database_now,
)
from studymate.infrastructure.external_delivery.models import (
    DeliverySourceRecord,
    ExternalDeliveryRecord,
)
from studymate.infrastructure.external_delivery.source_reads import SelectedSourceLoader
from studymate.infrastructure.persistence.base import Base
from tests.integration.migrations import migrate
from tests.integration.student_actor import actor

pytestmark = pytest.mark.integration


async def test_explicit_history_backfill_preserves_manual_truth_and_never_routes_telegram(
    engine: AsyncEngine,
) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(migrate, "0054_identity_recreation")
    owner = await actor(engine)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    identifier = uuid4()
    async with sessions.begin() as session:
        await session.execute(
            insert(Base.metadata.tables["product_events"]).values(
                id=identifier,
                account_id=owner.id,
                kind="auth.email_confirmed",
                occurrence_key=f"smv1:{uuid4().hex}:p:operator",
                schema_version=1,
                occurred_at=await database_now(session),
            )
        )
    async with engine.begin() as connection:
        await connection.run_sync(migrate, "head")
    async with sessions() as session:
        assert tuple(await session.scalars(select(DeliverySourceRecord))) == ()
    seed = SeedUmamiBackfill(SqlMaintenanceUnitOfWork(sessions))
    assert await seed((identifier,)) == 1
    assert await seed((identifier,)) == 0
    assert await MaterializeDeliverySources(SqlMaterializationUnitOfWork(sessions))() == 1
    async with sessions() as session:
        capture = (await session.scalars(select(DeliverySourceRecord))).one()
        assert capture.mode == "backfill_umami"
        delivery = (await session.scalars(select(ExternalDeliveryRecord))).one()
        assert delivery.sink == "umami"
        assert delivery.attempt_count == 0
        selected = (await SelectedSourceLoader(session).load((capture,)))[0]
        assert isinstance(selected.source, CanonicalSource)
        assert selected.source.membership_evidence == MembershipEvidence.MANUAL_PLACEHOLDER
