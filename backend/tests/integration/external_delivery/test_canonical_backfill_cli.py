"""Actual migrated history, atomic source validation and idempotent canonical capture."""

from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from deployment.backend.canonical_backfill import (
    BackfillRejectedError,
    CanonicalRef,
    Manifest,
    Plan,
    apply_plan,
    guard_database,
    helper_digest,
    make_plan,
    manifest_digest,
)
from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from studymate.application.external_delivery.routing import MaterializeDeliverySources
from studymate.domain.external_delivery.sources import CanonicalSource, MembershipEvidence
from studymate.domain.operator.timeline import OperatorEventKind
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
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from tests.integration.migrations import migrate
from tests.integration.student_actor import actor

pytestmark = pytest.mark.integration


async def history(engine: AsyncEngine) -> tuple[async_sessionmaker[AsyncSession], Plan, UUID]:
    async with engine.begin() as connection:
        await connection.run_sync(migrate, "0054_identity_recreation")
    owner = await actor(engine)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions.begin() as session:
        at = await database_now(session)
        await session.execute(
            insert(Base.metadata.tables["product_events"]),
            [
                {
                    "id": uuid4(),
                    "account_id": owner.id,
                    "kind": "auth.email_confirmed",
                    "occurrence_key": f"smv1:{uuid4().hex}:p:controlled_operator",
                    "schema_version": 1,
                    "occurred_at": at,
                },
                {
                    "id": uuid4(),
                    "account_id": owner.id,
                    "kind": "auth.email_confirmed",
                    "occurrence_key": f"smv1:{uuid4().hex}:p:controlled_operator",
                    "schema_version": 1,
                    "occurred_at": at,
                },
            ],
        )
    async with engine.begin() as connection:
        await connection.run_sync(migrate, "head")
    async with sessions.begin() as session:
        plan = await make_plan(session, uuid4(), "controlled_operator", await database_now(session))
    return sessions, plan, owner.id


async def test_actual_historical_plan_apply_resume_preserves_manual_truth_and_no_telegram(
    engine: AsyncEngine,
) -> None:
    sessions, plan, owner = await history(engine)
    assert plan.manifest.sources
    async with sessions.begin() as session:
        first = await apply_plan(session, plan)
    assert first["inserted_this_transaction"] == len(plan.manifest.sources)
    async with sessions() as session:
        before = tuple(
            (row.id, row.canonical_event_id, row.mode, row.captured_at)
            for row in (
                await session.scalars(
                    select(DeliverySourceRecord).order_by(DeliverySourceRecord.id)
                )
            ).all()
        )
    async with sessions.begin() as session:
        replay = await apply_plan(session, plan)
    assert replay["inserted_this_transaction"] == 0
    async with sessions() as session:
        after = tuple(
            (row.id, row.canonical_event_id, row.mode, row.captured_at)
            for row in (
                await session.scalars(
                    select(DeliverySourceRecord).order_by(DeliverySourceRecord.id)
                )
            ).all()
        )
        assert before == after
        events = tuple(
            (
                await session.scalars(select(ProductEventRecord).order_by(ProductEventRecord.id))
            ).all()
        )
        assert tuple(row.id for row in events) == tuple(ref.id for ref in plan.manifest.sources)
        assert all(row.account_id == owner and row.kind == "auth.email_confirmed" for row in events)
        assert tuple(row.occurred_at for row in events) == tuple(
            ref.occurred_at for ref in plan.manifest.sources
        )
    await MaterializeDeliverySources(SqlMaterializationUnitOfWork(sessions))()
    async with sessions() as session:
        deliveries = tuple((await session.scalars(select(ExternalDeliveryRecord))).all())
        assert deliveries
        assert all(row.sink == "umami" and row.attempt_count == 0 for row in deliveries)
        captures = tuple((await session.scalars(select(DeliverySourceRecord))).all())
        selected = await SelectedSourceLoader(session).load(captures)
        assert all(
            isinstance(row.source, CanonicalSource)
            and row.source.membership_evidence == MembershipEvidence.MANUAL_PLACEHOLDER
            for row in selected
        )
        final = await make_plan(session, uuid4(), "controlled_operator", plan.manifest.cutoff)
        assert final.manifest.sources == ()


@pytest.mark.parametrize("fault", ["missing_reference", "changed_metadata"])
async def test_selection_changes_roll_back_every_capture_before_seeding(
    engine: AsyncEngine,
    fault: str,
) -> None:
    sessions, plan, _owner = await history(engine)
    if fault == "missing_reference":
        async with sessions.begin() as session:
            await session.execute(
                delete(ProductEventRecord).where(
                    ProductEventRecord.id == plan.manifest.sources[-1].id
                )
            )
    else:
        ref = plan.manifest.sources[-1].model_copy(
            update={
                "occurred_at": plan.manifest.sources[-1].occurred_at - timedelta(seconds=1),
            }
        )
        manifest = plan.manifest.model_copy(update={"sources": (*plan.manifest.sources[:-1], ref)})
        plan = Plan(manifest=manifest, manifest_sha256=manifest_digest(manifest))
    with pytest.raises(BackfillRejectedError, match="canonical_selection_changed_or_missing"):
        async with sessions.begin() as session:
            await apply_plan(session, plan)
    async with sessions() as session:
        assert tuple(await session.scalars(select(DeliverySourceRecord))) == ()


async def test_actual_nonstaging_connection_is_rejected(engine: AsyncEngine) -> None:
    async with async_sessionmaker(engine).begin() as session:
        with pytest.raises(BackfillRejectedError, match="wrong_database_or_schema"):
            await guard_database(session)


async def test_existing_actual_live_trigger_capture_is_not_rebound(engine: AsyncEngine) -> None:
    sessions, _historical_plan, owner = await history(engine)
    identifier = uuid4()
    async with sessions.begin() as session:
        at = await database_now(session)
        await session.execute(
            insert(Base.metadata.tables["product_events"]).values(
                id=identifier,
                account_id=owner,
                kind="auth.email_confirmed",
                occurrence_key=f"smv1:{uuid4().hex}:p:controlled_operator",
                schema_version=1,
                occurred_at=at,
            )
        )
    async with sessions.begin() as session:
        captured = (
            await session.scalars(
                select(DeliverySourceRecord).where(
                    DeliverySourceRecord.canonical_event_id == identifier
                )
            )
        ).one()
        original = (captured.id, captured.mode, captured.captured_at)
        now = await database_now(session)
        manifest = Manifest(
            operation_id=uuid4(),
            performed_by="controlled_operator",
            cutoff=now,
            planned_at=now,
            helper_sha256=helper_digest(),
            more=False,
            sources=(
                CanonicalRef(id=identifier, kind=OperatorEventKind.EMAIL_CONFIRMED, occurred_at=at),
            ),
        )
        receipt = await apply_plan(
            session, Plan(manifest=manifest, manifest_sha256=manifest_digest(manifest))
        )
        assert receipt["inserted_this_transaction"] == 0
    async with sessions() as session:
        retained = (
            await session.scalars(
                select(DeliverySourceRecord).where(
                    DeliverySourceRecord.canonical_event_id == identifier
                )
            )
        ).one()
        assert (retained.id, retained.mode, retained.captured_at) == original
        assert retained.mode == "live"
