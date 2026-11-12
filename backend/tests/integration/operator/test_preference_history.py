from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from studymate.application.idempotency import IntentKey
from studymate.application.notification_preferences.preferences import (
    ChooseOwnNotificationPreference,
    ChoosePreferenceCommand,
)
from studymate.application.operator.preference_history import ReadOperatorPreferenceHistory
from studymate.domain.notification_preferences.state import NotificationMode
from studymate.domain.operator.audit import OperatorAudit
from studymate.domain.operator.preference_history import OPERATOR_PREFERENCE_HISTORY_PAGE_SIZE
from studymate.infrastructure.notification_preferences.models import PreferenceRevisionRecord
from studymate.infrastructure.notification_preferences.persistence import SqlPreferenceUnitOfWork
from studymate.infrastructure.operator.models import OperatorAuditRecord
from studymate.infrastructure.operator.preference_history_cursors import (
    FernetOperatorPreferenceHistoryCursorCodec,
)
from studymate.infrastructure.operator.preference_history_transactions import (
    SqlOperatorPreferenceHistoryUnitOfWork,
)
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import (
    record_notification_preference_event,
    record_operator_audit,
)
from tests.integration.operator.test_reads import operator
from tests.integration.requests.fixture import FINGERPRINTER, HASHER
from tests.integration.student_actor import actor

pytestmark = pytest.mark.integration
CODEC = FernetOperatorPreferenceHistoryCursorCodec.from_key(b"p" * 32)


def reader(engine: AsyncEngine) -> ReadOperatorPreferenceHistory:
    return ReadOperatorPreferenceHistory(
        SqlOperatorPreferenceHistoryUnitOfWork(
            async_sessionmaker(engine, expire_on_commit=False), record_operator_audit
        ),
        HASHER,
        CODEC,
    )


def writer(engine: AsyncEngine) -> ChooseOwnNotificationPreference:
    return ChooseOwnNotificationPreference(
        SqlPreferenceUnitOfWork(
            async_sessionmaker(engine, expire_on_commit=False), record_notification_preference_event
        ),
        HASHER,
        FINGERPRINTER,
    )


async def test_implicit_default_and_noop_choice_never_become_a_fake_stored_revision(
    identity_engine: AsyncEngine,
) -> None:
    viewer, target = await operator(identity_engine), await actor(identity_engine)
    no_change = await writer(identity_engine)(
        ChoosePreferenceCommand(
            target.credential,
            NotificationMode.MESSAGES_AND_REQUESTS,
            0,
            IntentKey("default-preference-noop"),
        )
    )
    assert no_change.version == 0
    assert no_change.changed_at is None
    read = reader(identity_engine)
    existing = await read(viewer.credential, target.id)
    assert existing is not None
    assert existing.current is None
    assert existing.revisions == ()
    assert existing.anchor_version == 0
    assert existing.next_cursor is None
    assert await read(viewer.credential, uuid4()) is None
    async with async_sessionmaker(identity_engine)() as session:
        assert tuple(await session.scalars(select(PreferenceRevisionRecord))) == ()
        audits = tuple(await session.scalars(select(OperatorAuditRecord)))
        assert {row.outcome for row in audits} == {"read", "not_found"}


async def test_actual_modes_and_original_history_survive_banned_deleted_subject(
    identity_engine: AsyncEngine,
) -> None:
    viewer, target = await operator(identity_engine), await actor(identity_engine)
    write = writer(identity_engine)
    first = await write(
        ChoosePreferenceCommand(
            target.credential, NotificationMode.ALL_UPDATES, 0, IntentKey("preference-all-updates")
        )
    )
    second = await write(
        ChoosePreferenceCommand(
            target.credential,
            NotificationMode.MESSAGES_AND_REQUESTS,
            first.version,
            IntentKey("preference-messages"),
        )
    )
    async with async_sessionmaker(identity_engine).begin() as session:
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == target.id)
            .values(deleted_at=func.clock_timestamp(), banned_at=func.clock_timestamp())
        )
    page = await reader(identity_engine)(viewer.credential, target.id)
    assert page is not None
    assert page.current is not None
    assert page.current.version == second.version
    assert page.current.mode == second.mode
    assert page.current.changed_at == second.changed_at
    assert tuple(row.version for row in page.revisions) == (second.version, first.version)
    assert tuple(row.mode for row in page.revisions) == (second.mode, first.mode)
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


async def test_actual_preference_pagination_keeps_history_anchor_and_current_head_distinct(
    identity_engine: AsyncEngine,
) -> None:
    viewer, target = await operator(identity_engine), await actor(identity_engine)
    write = writer(identity_engine)
    upper = OPERATOR_PREFERENCE_HISTORY_PAGE_SIZE + 2
    for version in range(upper):
        await write(
            ChoosePreferenceCommand(
                target.credential,
                NotificationMode.ALL_UPDATES
                if version % 2 == 0
                else NotificationMode.MESSAGES_AND_REQUESTS,
                version,
                IntentKey(str(uuid4())),
            )
        )
    read = reader(identity_engine)
    first = await read(viewer.credential, target.id)
    assert first is not None
    assert first.next_cursor is not None
    assert len(first.revisions) == OPERATOR_PREFERENCE_HISTORY_PAGE_SIZE
    assert first.anchor_version == upper
    latest = await write(
        ChoosePreferenceCommand(
            target.credential,
            NotificationMode.ALL_UPDATES,
            upper,
            IntentKey("later-preference-choice"),
        )
    )
    second = await read(viewer.credential, target.id, first.next_cursor)
    assert second is not None
    assert second.current is not None
    assert second.current.version == latest.version
    assert second.anchor_version == first.anchor_version
    assert tuple(row.version for row in second.revisions) == (2, 1)
    assert second.next_cursor is None


async def fail_inspection(session: AsyncSession, audit: OperatorAudit) -> None:
    await record_operator_audit(session, audit)
    raise RuntimeError("synthetic preference inspection failure")


async def test_canonical_audit_failure_rolls_back_without_returning_or_changing_preference(
    identity_engine: AsyncEngine,
) -> None:
    viewer, target = await operator(identity_engine), await actor(identity_engine)
    await writer(identity_engine)(
        ChoosePreferenceCommand(
            target.credential,
            NotificationMode.ALL_UPDATES,
            0,
            IntentKey("real-preference-before-failure"),
        )
    )
    unit = SqlOperatorPreferenceHistoryUnitOfWork(
        async_sessionmaker(identity_engine, expire_on_commit=False), fail_inspection
    )
    with pytest.raises(RuntimeError, match="synthetic preference inspection failure"):
        await ReadOperatorPreferenceHistory(unit, HASHER, CODEC)(viewer.credential, target.id)
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
        assert (await session.scalars(select(PreferenceRevisionRecord))).one().mode == "all_updates"
