from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from studymate.application.operator.visibility_history import ReadOperatorVisibilityHistory
from studymate.domain.operator.audit import OperatorAudit
from studymate.domain.operator.visibility_history import OPERATOR_VISIBILITY_HISTORY_PAGE_SIZE
from studymate.infrastructure.operator.models import OperatorAuditRecord
from studymate.infrastructure.operator.visibility_history_cursors import (
    FernetOperatorVisibilityHistoryCursorCodec,
)
from studymate.infrastructure.operator.visibility_history_transactions import (
    SqlOperatorVisibilityHistoryUnitOfWork,
)
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.onboarding_models import VisibilityRevisionRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import record_operator_audit
from tests.integration.operator.test_reads import operator
from tests.integration.profile_lifecycle_fixture import activated, command, services
from tests.integration.requests.fixture import HASHER
from tests.integration.student_actor import actor
from tests.integration.test_discovery_freshness import advance

pytestmark = pytest.mark.integration
CODEC = FernetOperatorVisibilityHistoryCursorCodec.from_key(b"v" * 32)


def reader(engine: AsyncEngine) -> ReadOperatorVisibilityHistory:
    return ReadOperatorVisibilityHistory(
        SqlOperatorVisibilityHistoryUnitOfWork(
            async_sessionmaker(engine, expire_on_commit=False), record_operator_audit
        ),
        HASHER,
        CODEC,
    )


async def test_existing_unactivated_account_has_no_invented_visible_revision(
    identity_engine: AsyncEngine,
) -> None:
    viewer, target = await operator(identity_engine), await actor(identity_engine)
    read = reader(identity_engine)
    page = await read(viewer.credential, target.id)
    assert page is not None
    assert page.current is None
    assert page.revisions == ()
    assert page.anchor_version == 0
    assert await read(viewer.credential, uuid4()) is None
    async with async_sessionmaker(identity_engine)() as session:
        audit = tuple(await session.scalars(select(OperatorAuditRecord)))
        assert {row.outcome for row in audit} == {"read", "not_found"}


async def test_initial_activation_is_one_actual_source_not_an_invented_restoration_event(
    identity_engine: AsyncEngine,
) -> None:
    target, viewer = await activated(identity_engine), await operator(identity_engine)
    page = await reader(identity_engine)(viewer.credential, target.id)
    assert page is not None
    assert page.current is not None
    assert page.current.version == 1
    assert page.current.hidden_at is None
    assert page.revisions == (page.current,)
    async with async_sessionmaker(identity_engine)() as session:
        source = (await session.scalars(select(VisibilityRevisionRecord))).one()
        assert page.current.completed_at == source.completed_at
        assert page.current.changed_at == source.changed_at
        assert (
            tuple(
                await session.scalars(
                    select(ProductEventRecord).where(
                        ProductEventRecord.account_id == target.id,
                        ProductEventRecord.kind.in_(("profile.hidden", "profile.restored")),
                        ProductEventRecord.visibility_version == 1,
                    )
                )
            )
            == ()
        )


async def test_hide_restore_sources_survive_subject_ban_and_soft_deletion(
    identity_engine: AsyncEngine,
) -> None:
    target, viewer = await activated(identity_engine), await operator(identity_engine)
    change, _ = services(identity_engine)
    hidden = await change(command(target))
    restored = await change(command(target, hidden=False, version=hidden.visibility_version))
    async with async_sessionmaker(identity_engine).begin() as session:
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == target.id)
            .values(banned_at=func.clock_timestamp(), deleted_at=func.clock_timestamp())
        )
    page = await reader(identity_engine)(viewer.credential, target.id)
    assert page is not None
    assert page.current is not None
    assert page.current.version == restored.visibility_version
    assert tuple(row.version for row in page.revisions) == (3, 2, 1)
    assert page.revisions[1].hidden_at == hidden.hidden_at
    assert page.revisions[0].hidden_at is None
    assert {row.completed_at for row in page.revisions} == {restored.completed_at}
    async with async_sessionmaker(identity_engine)() as session:
        audit = (await session.scalars(select(OperatorAuditRecord))).one()
        assert audit.action == "read_account"
        assert audit.requested_id == target.id
        assert audit.result_ids == [target.id]
        event = (
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind == "operator.inspected")
            )
        ).one()
        assert event.operator_audit_id == audit.id


async def test_actual_visibility_pagination_keeps_old_anchor_and_new_current_head(
    identity_engine: AsyncEngine,
) -> None:
    target, viewer = await activated(identity_engine), await operator(identity_engine)
    change, _ = services(identity_engine)
    changes = OPERATOR_VISIBILITY_HISTORY_PAGE_SIZE + 2
    for index in range(changes):
        await change(command(target, hidden=index % 2 == 0, version=index + 1))
    read = reader(identity_engine)
    first = await read(viewer.credential, target.id)
    assert first is not None
    assert first.next_cursor is not None
    assert first.anchor_version == changes + 1
    newest = await change(command(target, version=changes + 1))
    second = await read(viewer.credential, target.id, first.next_cursor)
    assert second is not None
    assert second.current is not None
    assert second.current.version == newest.visibility_version
    assert second.anchor_version == first.anchor_version
    assert tuple(row.version for row in second.revisions) == (3, 2, 1)
    assert second.next_cursor is None


async def test_actual_exposure_confirmation_reuses_visibility_revision_without_fake_history(
    identity_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target, viewer = await activated(identity_engine), await operator(identity_engine)
    # Existing controlled future-clock fixture; extend both real sessions before
    # checking historical metadata through the privileged reader.
    await advance(identity_engine, target.id, monkeypatch)
    await advance(identity_engine, viewer.id, monkeypatch)
    change, _ = services(identity_engine)
    confirmed = await change(command(target, hidden=False))
    assert confirmed.visibility_version == 1
    page = await reader(identity_engine)(viewer.credential, target.id)
    assert page is not None
    assert tuple(row.version for row in page.revisions) == (1,)
    assert page.current is not None
    assert page.current.changed_at == confirmed.changed_at
    async with async_sessionmaker(identity_engine)() as session:
        assert len(tuple(await session.scalars(select(VisibilityRevisionRecord)))) == 1
        assert (
            tuple(
                await session.scalars(
                    select(ProductEventRecord).where(
                        ProductEventRecord.account_id == target.id,
                        ProductEventRecord.kind.in_(("profile.hidden", "profile.restored")),
                        ProductEventRecord.visibility_version == 1,
                    )
                )
            )
            == ()
        )


async def fail_inspection(session: AsyncSession, audit: OperatorAudit) -> None:
    await record_operator_audit(session, audit)
    raise RuntimeError("synthetic visibility inspection failure")


async def test_canonical_audit_failure_returns_no_history_and_does_not_change_visibility(
    identity_engine: AsyncEngine,
) -> None:
    target, viewer = await activated(identity_engine), await operator(identity_engine)
    unit = SqlOperatorVisibilityHistoryUnitOfWork(
        async_sessionmaker(identity_engine, expire_on_commit=False), fail_inspection
    )
    with pytest.raises(RuntimeError, match="synthetic visibility inspection failure"):
        await ReadOperatorVisibilityHistory(unit, HASHER, CODEC)(viewer.credential, target.id)
    async with unit.sessions() as session:
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
        assert (await session.scalars(select(VisibilityRevisionRecord))).one().version == 1
