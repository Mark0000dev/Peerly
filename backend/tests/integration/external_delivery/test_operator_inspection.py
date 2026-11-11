"""Actual operator authority/audit rollback over retained selected source metadata."""

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from studymate.application.errors import StorageUnavailableError
from studymate.application.external_delivery.inspection import ReadDeliverySource
from studymate.application.operator.authority import OperatorAccessDeniedError
from studymate.domain.operator.audit import OperatorAudit
from studymate.infrastructure.external_delivery.inspection import SqlSourceInspectionUnitOfWork
from studymate.infrastructure.external_delivery.materialization import database_now
from studymate.infrastructure.external_delivery.models import DeliverySourceRecord
from studymate.infrastructure.operator.models import OperatorAuditRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import record_operator_audit
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.integration.operator.test_reads import operator
from tests.integration.student_actor import actor

pytestmark = pytest.mark.integration


async def fail_audit(session: AsyncSession, audit: OperatorAudit) -> None:
    await record_operator_audit(session, audit)
    raise StorageUnavailableError


async def test_exact_source_inspection_requires_role_and_committed_audit(
    identity_engine: AsyncEngine,
) -> None:
    owner = await operator(identity_engine)
    student = await actor(identity_engine)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    async with sessions.begin() as session:
        event = ProductEventRecord(
            id=uuid4(),
            account_id=student.id,
            kind="auth.email_confirmed",
            occurrence_key=f"smv1:{uuid4().hex}:p:operator",
            schema_version=1,
            occurred_at=await database_now(session),
        )
        session.add(event)
        await session.flush()
        source = (
            await session.scalars(
                select(DeliverySourceRecord).where(
                    DeliverySourceRecord.canonical_event_id == event.id
                )
            )
        ).one()
        source_id = source.id
    read = ReadDeliverySource(
        SqlSourceInspectionUnitOfWork(sessions, record_operator_audit), Sha256SessionHasher()
    )
    with pytest.raises(OperatorAccessDeniedError):
        await read(student.credential, source_id)
    detail = await read(owner.credential, source_id)
    assert detail is not None
    assert detail.summary.actor_id == student.id
    assert detail.summary.original_id == event.id
    assert detail.summary.materialized_at is None
    assert detail.deliveries == ()
    failing = ReadDeliverySource(
        SqlSourceInspectionUnitOfWork(sessions, fail_audit), Sha256SessionHasher()
    )
    with pytest.raises(StorageUnavailableError):
        await failing(owner.credential, source_id)
    async with sessions() as session:
        audits = tuple(await session.scalars(select(OperatorAuditRecord)))
        assert len(audits) == 1
        assert audits[0].requested_id == source_id
        assert audits[0].result_ids == [source_id]
