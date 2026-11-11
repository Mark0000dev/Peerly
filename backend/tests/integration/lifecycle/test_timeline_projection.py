"""Head46 reverse-target lookup over an actual retained lifecycle source, audited as usual."""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.idempotency import IntentKey
from studymate.application.lifecycle.commands import ChangeAccountBanCommand
from studymate.application.operator.timeline import SearchOperatorEvents
from studymate.application.operator.timeline_ports import OperatorEventFilters
from studymate.domain.lifecycle.states import LifecycleReason
from studymate.domain.operator.timeline import OperatorEventKind, OperatorSourceKind
from studymate.infrastructure.operator.timeline_cursors import FernetOperatorEventCursorCodec
from studymate.infrastructure.operator.timeline_transactions import SqlOperatorTimelineUnitOfWork
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import record_operator_audit
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.integration.lifecycle.test_transactions import usecase
from tests.integration.operator.test_reads import operator
from tests.integration.student_actor import actor

pytestmark = pytest.mark.integration


async def test_lifecycle_source_is_findable_by_actual_actor_and_target(
    identity_engine: AsyncEngine,
) -> None:
    owner, target = await operator(identity_engine), await actor(identity_engine)
    changed = await usecase(identity_engine)(
        ChangeAccountBanCommand(
            owner.credential,
            target.id,
            True,
            LifecycleReason("private retained reason"),
            IntentKey("timeline-ban"),
        )
    )
    source = changed.revision
    assert source is not None
    event_id = uuid4()
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    # Projection fixture uses actual source composite FK. This is not acceptance of
    # the main atomic canonical writer/effects callback (validated separately).
    async with sessions.begin() as session:
        session.add(
            ProductEventRecord(
                id=event_id,
                account_id=owner.id,
                kind="account.lifecycle_changed",
                schema_version=1,
                occurrence_key=f"lifecycle:{source.id}",
                occurred_at=source.changed_at,
                lifecycle_revision_id=source.id,
                lifecycle_account_id=target.id,
                lifecycle_version=source.version,
                lifecycle_operation=source.operation.value,
            )
        )
    search = SearchOperatorEvents(
        SqlOperatorTimelineUnitOfWork(sessions, record_operator_audit),
        Sha256SessionHasher(),
        HmacIntentFingerprinter(b"t" * 32),
        FernetOperatorEventCursorCodec.from_key(b"t" * 32),
    )
    for account_id in (owner.id, target.id):
        page = await search(
            owner.credential,
            OperatorEventFilters(
                subject_account_id=account_id,
                kind=OperatorEventKind.ACCOUNT_LIFECYCLE_CHANGED,
            ),
        )
        assert len(page.events) == 1
        event = page.events[0]
        assert event.id == event_id
        assert event.subject_account_id == owner.id
        assert event.sources[0].kind == OperatorSourceKind.LIFECYCLE
        assert event.sources[0].owner_id == owner.id
        assert event.sources[0].related_account_id == target.id
        assert event.facts.lifecycle_operation == source.operation
    unrelated = await actor(identity_engine)
    assert not (
        await search(
            owner.credential,
            OperatorEventFilters(
                subject_account_id=unrelated.id,
                kind=OperatorEventKind.ACCOUNT_LIFECYCLE_CHANGED,
            ),
        )
    ).events
