from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from studymate.application.idempotency import IntentKey
from studymate.application.lifecycle.commands import ChangeAccountBanCommand
from studymate.application.operator.lifecycle_history import ReadOperatorLifecycleHistory
from studymate.domain.lifecycle.states import LifecycleReason
from studymate.domain.operator.audit import OperatorAudit
from studymate.domain.operator.lifecycle_history import OPERATOR_LIFECYCLE_HISTORY_PAGE_SIZE
from studymate.infrastructure.lifecycle.models import LifecycleRevisionRecord
from studymate.infrastructure.operator.lifecycle_history_cursors import (
    FernetOperatorLifecycleHistoryCursorCodec,
)
from studymate.infrastructure.operator.lifecycle_history_transactions import (
    SqlOperatorLifecycleHistoryUnitOfWork,
)
from studymate.infrastructure.operator.models import OperatorAuditRecord
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import record_operator_audit
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.integration.lifecycle.test_transactions import usecase
from tests.integration.operator.test_reads import operator
from tests.integration.student_actor import actor

pytestmark = pytest.mark.integration
EXPECTED_READ_AUDITS = 3


async def test_retained_ban_unban_sources_keep_exact_original_provenance(
    identity_engine: AsyncEngine,
) -> None:
    viewer, target = await operator(identity_engine), await actor(identity_engine)
    for banned in (True, False):
        await usecase(identity_engine)(
            ChangeAccountBanCommand(
                viewer.credential,
                target.id,
                banned,
                LifecycleReason("  private exact historical reason  "),
                IntentKey(f"history-{banned}"),
            )
        )
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    read = ReadOperatorLifecycleHistory(
        SqlOperatorLifecycleHistoryUnitOfWork(sessions, record_operator_audit),
        Sha256SessionHasher(),
        FernetOperatorLifecycleHistoryCursorCodec.from_key(b"h" * 32),
    )
    async with sessions.begin() as session:
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == target.id)
            .values(deleted_at=func.clock_timestamp())
        )
    page = await read(viewer.credential, target.id)
    assert page is not None
    assert tuple(row.version for row in page.revisions) == (2, 1)
    async with sessions() as session:
        sources = tuple(
            await session.scalars(
                select(LifecycleRevisionRecord).order_by(LifecycleRevisionRecord.version.desc())
            )
        )
        for returned, source in zip(page.revisions, sources, strict=True):
            assert returned.id == source.id
            assert returned.actor_id == viewer.id
            assert returned.actor_session_id == source.actor_session_id
            assert returned.operator_access_version == source.operator_access_version
            assert returned.reason == source.reason
            assert returned.changed_at == source.changed_at
            assert returned.before_banned_at == source.before_banned_at
            assert returned.after_banned_at == source.after_banned_at
    empty = await read(viewer.credential, viewer.id)
    assert empty is not None
    assert empty.revisions == ()
    assert empty.anchor_version == 0
    assert await read(viewer.credential, uuid4()) is None
    async with sessions() as session:
        audits = tuple(await session.scalars(select(OperatorAuditRecord)))
        assert len(audits) == EXPECTED_READ_AUDITS
        assert any(row.outcome == "not_found" for row in audits)
        events = tuple(
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind == "operator.inspected")
            )
        )
        assert {row.operator_audit_id for row in events} == {row.id for row in audits}


async def test_actual_version_pagination_preserves_anchor_after_new_transition(
    identity_engine: AsyncEngine,
) -> None:
    viewer, target = await operator(identity_engine), await actor(identity_engine)
    writer = usecase(identity_engine)
    for index in range(52):
        await writer(
            ChangeAccountBanCommand(
                viewer.credential,
                target.id,
                index % 2 == 0,
                LifecycleReason("pagination evidence"),
                IntentKey(f"history-page-{index}"),
            )
        )
    read = ReadOperatorLifecycleHistory(
        SqlOperatorLifecycleHistoryUnitOfWork(
            async_sessionmaker(identity_engine, expire_on_commit=False),
            record_operator_audit,
        ),
        Sha256SessionHasher(),
        FernetOperatorLifecycleHistoryCursorCodec.from_key(b"h" * 32),
    )
    first = await read(viewer.credential, target.id)
    assert first is not None
    assert len(first.revisions) == OPERATOR_LIFECYCLE_HISTORY_PAGE_SIZE
    assert first.next_cursor is not None
    await writer(
        ChangeAccountBanCommand(
            viewer.credential,
            target.id,
            True,
            LifecycleReason("new transition"),
            IntentKey("page-new"),
        )
    )
    second = await read(viewer.credential, target.id, first.next_cursor)
    assert second is not None
    assert tuple(row.version for row in second.revisions) == (2, 1)
    assert second.anchor_version == first.anchor_version
    assert second.next_cursor is None


async def fail_audit(session: AsyncSession, audit: OperatorAudit) -> None:
    await record_operator_audit(session, audit)
    raise RuntimeError("synthetic canonical inspection failure")


async def test_canonical_audit_failure_rolls_back_inspection_and_returns_no_history(
    identity_engine: AsyncEngine,
) -> None:
    viewer, target = await operator(identity_engine), await actor(identity_engine)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    read = ReadOperatorLifecycleHistory(
        SqlOperatorLifecycleHistoryUnitOfWork(sessions, fail_audit),
        Sha256SessionHasher(),
        FernetOperatorLifecycleHistoryCursorCodec.from_key(b"h" * 32),
    )
    with pytest.raises(RuntimeError, match="synthetic canonical inspection failure"):
        await read(viewer.credential, target.id)
    async with sessions() as session:
        assert tuple(await session.scalars(select(OperatorAuditRecord))) == ()
        assert (
            tuple(
                await session.scalars(
                    select(ProductEventRecord).where(
                        ProductEventRecord.kind == "operator.inspected"
                    )
                )
            )
            == ()
        )
