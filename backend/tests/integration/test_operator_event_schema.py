from datetime import UTC, datetime
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.domain.membership import GOOGLE_ISSUER
from studymate.domain.operator.access import OperatorAccess
from studymate.domain.operator.audit import OperatorAction, OperatorAudit, OperatorAuditOutcome
from studymate.infrastructure.operator.models import (
    OperatorAccessRecord,
    OperatorAccessRevisionRecord,
    OperatorAuditRecord,
)
from studymate.infrastructure.persistence.discovery_freshness_models import DiscoveryExposureRecord
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    ExternalIdentityRecord,
)
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import record_operator_audit

pytestmark = pytest.mark.integration


async def seeded_audit(engine: AsyncEngine) -> OperatorAudit:
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    owner = uuid4()
    async with sessions.begin() as session:
        now = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        session.add(AccountRecord(id=owner, created_at=now))
        await session.flush()
        session.add(
            ExternalIdentityRecord(
                id=uuid4(),
                account_id=owner,
                issuer=GOOGLE_ISSUER,
                subject=f"synthetic-{owner}",
                created_at=now,
            )
        )
        await session.flush()
        session.add(OperatorAccessRecord(account_id=owner, current_version=1))
        await session.flush()
        session.add(
            OperatorAccessRevisionRecord(account_id=owner, version=1, active=True, changed_at=now)
        )
        await session.flush()
        audit = OperatorAudit(
            uuid4(),
            OperatorAccess(owner, 1, True, now),
            OperatorAction.SEARCH_ACCOUNTS,
            None,
            (),
            now,
            OperatorAuditOutcome.SEARCH,
            b"a" * 32,
        )
        session.add(
            OperatorAuditRecord(
                id=audit.id,
                operator_id=owner,
                operator_access_version=1,
                operator_access_active=True,
                action=audit.action.value,
                resource_kind="account",
                requested_id=None,
                result_ids=[],
                outcome=audit.outcome.value,
                query_fingerprint=audit.query_fingerprint,
                occurred_at=audit.at,
            )
        )
    return audit


async def test_operator_canonical_event_references_actual_audit_without_student_activity(
    identity_engine: AsyncEngine,
) -> None:
    audit = await seeded_audit(identity_engine)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    async with sessions.begin() as session:
        await record_operator_audit(session, audit)
    async with sessions() as session:
        event = (await session.scalars(select(ProductEventRecord))).one()
        assert event.kind == "operator.inspected"
        assert event.account_id == audit.access.account_id
        assert event.operator_audit_id == audit.id
        assert event.operator_action == audit.action.value
        assert event.operator_access_version == audit.access.version
        assert event.occurred_at == audit.at
        assert not tuple(await session.scalars(select(DiscoveryExposureRecord)))
        assert event.request_id is None
        assert event.trace_id is None


@pytest.mark.parametrize(
    "malformation", ["wrong_operator", "wrong_revision", "wrong_action", "mixed_family"]
)
async def test_operator_event_source_owner_revision_action_and_family_cannot_be_forged(
    identity_engine: AsyncEngine,
    malformation: str,
) -> None:
    audit = await seeded_audit(identity_engine)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    owner = audit.access.account_id
    if malformation == "wrong_operator":
        owner = uuid4()
        async with sessions.begin() as session:
            session.add(AccountRecord(id=owner, created_at=datetime.now(UTC)))
    event = ProductEventRecord(
        id=uuid4(),
        account_id=owner,
        kind="operator.inspected",
        occurrence_key=f"operator-audit:{uuid4()}",
        schema_version=1,
        occurred_at=audit.at,
        operator_audit_id=audit.id,
        operator_access_version=2 if malformation == "wrong_revision" else 1,
        operator_action="read_account" if malformation == "wrong_action" else audit.action.value,
        topic_present=True if malformation == "mixed_family" else None,
    )
    async with sessions() as session:
        session.add(event)
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()
    async with sessions() as session:
        assert not tuple(await session.scalars(select(ProductEventRecord)))


async def test_downgrade_refuses_to_purge_actual_operator_grants_or_audit_history(
    identity_engine: AsyncEngine,
) -> None:
    audit = await seeded_audit(identity_engine)

    def downgrade(connection: Connection) -> None:
        configuration = Config("alembic.ini")
        configuration.attributes["connection"] = connection
        command.downgrade(configuration, "0033_conversation_goal_shares")

    with pytest.raises(RuntimeError, match="retained operator grants or inspection audit history"):
        async with identity_engine.begin() as connection:
            await connection.run_sync(downgrade)
    async with async_sessionmaker(identity_engine)() as session:
        assert await session.get(OperatorAuditRecord, audit.id) is not None
        assert await session.get(OperatorAccessRecord, audit.access.account_id) is not None
