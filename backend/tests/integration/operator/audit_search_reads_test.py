"""Actual57 journal search: original grants, requested metadata, correlation and atomic audit."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from opentelemetry.sdk.trace import TracerProvider
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from studymate.application.errors import StorageUnavailableError
from studymate.application.operator.audit_search import SearchOperatorAudits
from studymate.application.operator.audit_search_ports import OperatorAuditFilters
from studymate.application.operator.authority import OperatorAccessDeniedError, require_operator
from studymate.application.ports.http_tracing import HttpExecution
from studymate.domain.operator.audit import (
    OPERATOR_EVENT_PAGE_SIZE,
    OperatorAction,
    OperatorAudit,
    OperatorAuditOutcome,
    OperatorResourceKind,
    OperatorResourceRef,
)
from studymate.infrastructure.observability.tracing import OtelHttpTracing
from studymate.infrastructure.operator.audit_search_cursors import FernetOperatorAuditCursorCodec
from studymate.infrastructure.operator.audit_search_transactions import (
    SqlOperatorAuditSearchTransaction,
    SqlOperatorAuditSearchUnitOfWork,
)
from studymate.infrastructure.operator.models import (
    OperatorAccessRecord,
    OperatorAccessRevisionRecord,
    OperatorAuditRecord,
)
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.product_events import record_operator_audit
from tests.integration.operator.test_reads import operator
from tests.integration.requests.fixture import FINGERPRINTER, HASHER
from tests.integration.student_actor import Actor, actor

pytestmark = pytest.mark.integration
CODEC = FernetOperatorAuditCursorCodec.from_key(b"k" * 32)


@dataclass(frozen=True, slots=True)
class Audits:
    sessions: async_sessionmaker[AsyncSession]
    original: Actor
    viewer: Actor
    target: Actor
    ids: tuple[UUID, ...]
    at: datetime
    request_id: UUID
    action_id: UUID

    def search(self) -> SearchOperatorAudits:
        return SearchOperatorAudits(
            SqlOperatorAuditSearchUnitOfWork(self.sessions, record_operator_audit),
            HASHER,
            FINGERPRINTER,
            CODEC,
        )


async def prepared(engine: AsyncEngine, count: int = OPERATOR_EVENT_PAGE_SIZE + 1) -> Audits:
    original, viewer, target = await operator(engine), await operator(engine), await actor(engine)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    request_id, action_id = uuid4(), uuid4()
    provider = TracerProvider()
    tracing = OtelHttpTracing(provider.get_tracer("audit-search-fixture"))
    identifiers: list[UUID] = []
    try:
        with tracing.start(
            HttpExecution(request_id, action_id, "GET", f"00-{'a' * 32}-{'b' * 16}-01")
        ):
            async with sessions.begin() as session:
                transaction = SqlOperatorAuditSearchTransaction(session, record_operator_audit)
                principal = await require_operator(transaction, original.credential, HASHER)
                at = await transaction.now()
                ref = OperatorResourceRef(OperatorResourceKind.ACCOUNT, target.id)
                for _ in range(count):
                    identifier = uuid4()
                    await transaction.save_operator_audit(
                        OperatorAudit(
                            identifier,
                            principal.access,
                            OperatorAction.READ_ACCOUNT,
                            ref,
                            (ref,),
                            at,
                            OperatorAuditOutcome.READ,
                        )
                    )
                    identifiers.append(identifier)
                # Same result-family with no requested target must not match target filters.
                await transaction.save_operator_audit(
                    OperatorAudit(
                        uuid4(),
                        principal.access,
                        OperatorAction.SEARCH_ACCOUNTS,
                        None,
                        (ref,),
                        at,
                        OperatorAuditOutcome.SEARCH,
                        b"f" * 32,
                    )
                )
    finally:
        provider.shutdown()
    return Audits(sessions, original, viewer, target, tuple(identifiers), at, request_id, action_id)


async def test_anchor_keyset_and_new_search_refs_only_visible_rows(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    filters = OperatorAuditFilters(operator_id=api.original.id, action=OperatorAction.READ_ACCOUNT)
    page = await api.search()(api.viewer.credential, filters)
    assert len(page.audits) == OPERATOR_EVENT_PAGE_SIZE
    assert page.next_cursor is not None
    assert (
        tuple(row.audit.id for row in page.audits)
        == tuple(sorted(api.ids, reverse=True))[:OPERATOR_EVENT_PAGE_SIZE]
    )
    rest = await api.search()(api.viewer.credential, filters, page.next_cursor)
    assert len(rest.audits) == 1
    assert rest.audits[0].audit.id == min(api.ids)
    assert rest.search_anchor_at == page.search_anchor_at
    async with api.sessions() as session:
        inspections = tuple(
            await session.scalars(
                select(OperatorAuditRecord)
                .where(OperatorAuditRecord.action == "search_audits")
                .order_by(OperatorAuditRecord.occurred_at)
            )
        )
        assert len(inspections) == len((page, rest))
        assert inspections[0].result_ids == [row.audit.id for row in page.audits]
        assert inspections[1].result_ids == [rest.audits[0].audit.id]
        assert all(
            row.requested_id is None and row.query_fingerprint is not None for row in inspections
        )


async def test_exact_requested_and_correlation_filters_retain_deleted_revoked_original_grant(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine, count=1)
    async with api.sessions.begin() as session:
        at = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(at, datetime)
        await session.execute(
            select(OperatorAccessRecord)
            .where(OperatorAccessRecord.account_id == api.original.id)
            .with_for_update()
        )
        session.add(
            OperatorAccessRevisionRecord(
                account_id=api.original.id, version=2, active=False, changed_at=at
            )
        )
        await session.flush()
        await session.execute(
            update(OperatorAccessRecord)
            .where(OperatorAccessRecord.account_id == api.original.id)
            .values(current_version=2)
        )
        await session.execute(
            update(AccountRecord).where(AccountRecord.id == api.original.id).values(deleted_at=at)
        )
    filters = OperatorAuditFilters(
        operator_id=api.original.id,
        requested_kind=OperatorResourceKind.ACCOUNT,
        requested_id=api.target.id,
        http_request_id=api.request_id,
        action_id=api.action_id,
        trace_id="a" * 32,
        occurred_from=api.at,
        occurred_before=api.at + timedelta(microseconds=1),
    )
    page = await api.search()(api.viewer.credential, filters)
    assert len(page.audits) == 1
    historical = page.audits[0].audit
    assert historical.id == api.ids[0]
    assert historical.access.account_id == api.original.id
    assert historical.access.version == 1
    assert historical.access.active
    # The historical grant is never a grant for a present caller without an operator role.
    with pytest.raises(OperatorAccessDeniedError):
        await api.search()(api.target.credential, filters)
    async with api.sessions() as session:
        record = (
            await session.scalars(
                select(OperatorAuditRecord).where(OperatorAuditRecord.action == "search_audits")
            )
        ).one()
        assert record.result_ids == [historical.id]
        assert record.operator_id == api.viewer.id


async def fail_canonical(session: AsyncSession, audit: OperatorAudit) -> None:
    await record_operator_audit(session, audit)
    raise StorageUnavailableError


async def test_canonical_failure_rolls_back_search_audit_before_metadata_return(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine, count=1)
    search = SearchOperatorAudits(
        SqlOperatorAuditSearchUnitOfWork(api.sessions, fail_canonical), HASHER, FINGERPRINTER, CODEC
    )
    with pytest.raises(StorageUnavailableError):
        await search(api.viewer.credential, OperatorAuditFilters())
    async with api.sessions() as session:
        assert (
            tuple(
                await session.scalars(
                    select(OperatorAuditRecord.id).where(
                        OperatorAuditRecord.action == "search_audits"
                    )
                )
            )
            == ()
        )
