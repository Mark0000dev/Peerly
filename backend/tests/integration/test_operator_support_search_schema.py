"""Actual support-search audit/canonical source and retention-safe downgrade."""

from dataclasses import replace

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.domain.operator.audit import OperatorAction, OperatorResourceKind
from studymate.infrastructure.operator.models import (
    OperatorAccessRevisionRecord,
    OperatorAuditRecord,
)
from studymate.infrastructure.operator.timeline_values import audit_value
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import record_operator_audit
from tests.integration.migrations import run_revision_step
from tests.integration.test_operator_event_schema import seeded_audit

pytestmark = pytest.mark.integration


async def test_actual_empty_support_search_is_audited_canonical_and_cannot_be_discarded(
    identity_engine: AsyncEngine,
) -> None:
    seed = await seeded_audit(identity_engine)
    audit = replace(seed, action=OperatorAction.SEARCH_SUPPORT_CASES)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    async with sessions.begin() as session:
        await session.execute(
            update(OperatorAuditRecord)
            .where(OperatorAuditRecord.id == audit.id)
            .values(action=audit.action.value, resource_kind="support_case")
        )
        await record_operator_audit(session, audit)
    async with sessions() as session:
        row = await session.get(OperatorAuditRecord, audit.id)
        grant = await session.get(
            OperatorAccessRevisionRecord, (audit.access.account_id, audit.access.version)
        )
        assert row is not None
        assert grant is not None
        detail = audit_value(row, grant)
        assert detail.audit.action == OperatorAction.SEARCH_SUPPORT_CASES
        assert detail.audit.results == ()
        assert OperatorResourceKind.SUPPORT_CASE.value == row.resource_kind
        event = (await session.scalars(select(ProductEventRecord))).one()
        assert event.operator_audit_id == audit.id
        assert event.operator_action == audit.action.value
    async with identity_engine.begin() as connection:
        with pytest.raises(RuntimeError, match="retained support-search audit"):
            await connection.run_sync(
                run_revision_step, "0053_operator_support_search", "downgrade"
            )
