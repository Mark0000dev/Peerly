"""Actual peer-feedback source histories; no student threshold/reconstruction/moderation writes."""

import asyncio
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from studymate.application.errors import StorageUnavailableError
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.operator.cursors import InvalidOperatorCursorError
from studymate.application.operator.feedback_ports import (
    OperatorFeedbackDirection,
    OperatorFeedbackFilters,
)
from studymate.application.operator.peer_feedback import (
    OperatorFeedbackHistoryPage,
    OperatorFeedbackRemovalsPage,
    OperatorFeedbackRootsPage,
    ReadOperatorFeedback,
    ReadOperatorFeedbackHistory,
    ReadOperatorFeedbackRemovals,
)
from studymate.domain.feedback.assessments import FeedbackRevision
from studymate.domain.operator.audit import OperatorAudit
from studymate.domain.operator.peer_feedback import (
    MAX_OPERATOR_FEEDBACK_TEXT,
    OPERATOR_FEEDBACK_PAGE_SIZE,
)
from studymate.infrastructure.feedback.models import (
    FeedbackCommandIntentRecord,
    PeerFeedbackRecord,
    PeerFeedbackRemovalRecord,
    PeerFeedbackRevisionRecord,
    StudyOutcomeRevisionRecord,
    StudyPromptReceiptRecord,
)
from studymate.infrastructure.operator.feedback_cursors import FernetOperatorFeedbackCursorCodec
from studymate.infrastructure.operator.feedback_transactions import (
    SqlOperatorFeedbackTransaction,
    SqlOperatorFeedbackUnitOfWork,
)
from studymate.infrastructure.operator.models import OperatorAccessRecord, OperatorAuditRecord
from studymate.infrastructure.persistence.catalogue_models import SubjectRecord
from studymate.infrastructure.persistence.identity_models import AccountRecord, SessionRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import record_operator_audit
from tests.integration.feedback.fixture import FeedbackServices
from tests.integration.feedback.fixture import prepared as feedback_prepared
from tests.integration.operator.test_reads import operator
from tests.integration.requests.fixture import FINGERPRINTER, HASHER, action, additional_peer, sent
from tests.integration.student_actor import Actor, actor
from tests.integration.test_message_commands import Chat

pytestmark = pytest.mark.integration
CODEC = FernetOperatorFeedbackCursorCodec.from_key(b"f" * 32)
HIGHEST_RETAINED_VERSION = 99
RAW_NOTE = "  Private retained raw team note\n  with original spaces  "
RAW_REASON = "  Private retained moderation reason\n with original spaces  "


@dataclass(frozen=True, slots=True)
class Feedback:
    api: FeedbackServices
    revision: FeedbackRevision
    owner: Actor
    uow: SqlOperatorFeedbackUnitOfWork

    def roots(self) -> ReadOperatorFeedback:
        return ReadOperatorFeedback(self.uow, HASHER, FINGERPRINTER, CODEC)

    def history(self) -> ReadOperatorFeedbackHistory:
        return ReadOperatorFeedbackHistory(self.uow, HASHER, CODEC)

    def removals(self) -> ReadOperatorFeedbackRemovals:
        return ReadOperatorFeedbackRemovals(self.uow, HASHER, CODEC)

    async def read(
        self, kind: str
    ) -> (
        OperatorFeedbackRootsPage
        | OperatorFeedbackHistoryPage
        | OperatorFeedbackRemovalsPage
        | None
    ):
        account = self.revision.reviewer_id
        if kind == "roots":
            return await self.roots()(self.owner.credential, account, OperatorFeedbackFilters())
        if kind == "history":
            return await self.history()(self.owner.credential, account, self.revision.id)
        return await self.removals()(self.owner.credential, account, self.revision.id)


async def prepared(engine: AsyncEngine, *, exchange: bool = True) -> Feedback:
    api = await feedback_prepared(engine)
    if exchange:
        await api.exchange()
    await api.outcomes()(api.outcome())
    review = await api.feedback()(api.review())
    return Feedback(
        api,
        review,
        await operator(engine),
        SqlOperatorFeedbackUnitOfWork(api.uow.sessions, record_operator_audit),
    )


def retained_revision(
    source: PeerFeedbackRevisionRecord, version: int
) -> PeerFeedbackRevisionRecord:
    return PeerFeedbackRevisionRecord(
        feedback_id=source.feedback_id,
        version=version,
        conversation_id=source.conversation_id,
        reviewer_id=source.reviewer_id,
        partner_id=source.partner_id,
        low_id=source.low_id,
        high_id=source.high_id,
        worked_confirmation_id=source.worked_confirmation_id,
        worked_answer=source.worked_answer,
        low_message_id=source.low_message_id,
        high_message_id=source.high_message_id,
        again="maybe",
        descriptors=["supportive", "easy_to_communicate"],
        team_note=RAW_NOTE,
        changed_at=source.changed_at - timedelta(minutes=version),
        http_request_id=uuid4(),
        action_id=uuid4(),
        trace_id="a" * 32,
        span_id="b" * 16,
    )


async def seed_removals(session: AsyncSession, api: Feedback, count: int) -> tuple[UUID, ...]:
    identifiers = tuple(UUID(int=10000 + index) for index in range(count))
    for identifier in identifiers:
        session.add(
            PeerFeedbackRemovalRecord(
                id=identifier,
                feedback_id=api.revision.id,
                source_version=1,
                operator_id=api.owner.id,
                operator_access_version=1,
                operator_access_active=True,
                kind="fraudulent",
                reason=RAW_REASON,
                removed_at=api.revision.changed_at + timedelta(days=1),
                http_request_id=uuid4(),
                action_id=uuid4(),
                trace_id="c" * 32,
                span_id="d" * 16,
            )
        )
    await session.flush()
    return identifiers


async def source_counts(session: AsyncSession) -> tuple[int, ...]:
    counts = []
    for model in (
        PeerFeedbackRecord,
        PeerFeedbackRevisionRecord,
        PeerFeedbackRemovalRecord,
        StudyOutcomeRevisionRecord,
        StudyPromptReceiptRecord,
        FeedbackCommandIntentRecord,
    ):
        value = await session.scalar(select(func.count()).select_from(model))
        assert value is not None
        counts.append(value)
    return tuple(counts)


async def test_all_raw_revision_history_both_participants_no_student_filter_or_decoder(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    async with api.uow.sessions.begin() as session:
        source = await session.get(PeerFeedbackRevisionRecord, (api.revision.id, 1))
        assert source is not None
        for version in (*range(2, OPERATOR_FEEDBACK_PAGE_SIZE + 4), HIGHEST_RETAINED_VERSION):
            session.add(retained_revision(source, version))
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == api.revision.reviewer_id)
            .values(banned_at=source.changed_at, deleted_at=source.changed_at)
        )
        before = await source_counts(session)
    for account in (api.revision.reviewer_id, api.revision.partner_id):
        first = await api.history()(api.owner.credential, account, api.revision.id)
        assert first is not None
        assert first.root.current_version == 1
        assert first.anchor_version == HIGHEST_RETAINED_VERSION
        assert first.next_cursor is not None
        assert len(first.revisions) == OPERATOR_FEEDBACK_PAGE_SIZE
        assert first.revisions[0].team_note == RAW_NOTE
        assert first.revisions[0].descriptors == ("supportive", "easy_to_communicate")
        assert first.revisions[0].again == "maybe"
        assert first.revisions[0].origin.trace_id == "a" * 32
        assert first.revisions[0].worked_confirmation_id == api.revision.worked_confirmation.id
        assert first.revisions[0].low_message_id is not None
        assert first.revisions[0].high_message_id is not None
        assert RAW_NOTE not in repr(first)
    assert first is not None
    assert first.next_cursor is not None
    last = await api.history()(api.owner.credential, account, api.revision.id, first.next_cursor)
    assert last is not None
    assert tuple(row.version for row in last.revisions) == (4, 3, 2, 1)
    assert not last.next_cursor
    async with api.uow.sessions() as session:
        assert await source_counts(session) == before
        assert await session.scalar(select(PeerFeedbackRecord.current_version)) == 1
        assert await session.scalar(select(func.count()).select_from(OperatorAuditRecord)) == len(
            (1, 2, 3)
        )


async def test_unbounded_removal_history_exact_pointer_pages_and_late_arrival(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    async with api.uow.sessions.begin() as session:
        identifiers = await seed_removals(session, api, OPERATOR_FEEDBACK_PAGE_SIZE + 3)
        await session.execute(
            update(PeerFeedbackRecord)
            .where(PeerFeedbackRecord.id == api.revision.id)
            .values(current_removal_id=identifiers[0])
        )
        before = await source_counts(session)
    first = await api.removals()(api.owner.credential, api.revision.partner_id, api.revision.id)
    assert first is not None
    assert first.next_cursor is not None
    assert first.root.current_removal_id == identifiers[0]
    assert first.removals[0].id == identifiers[-1]
    assert first.anchor_removed_at is not None
    assert first.anchor_removed_at > first.observed_at
    assert first.removals[0].reason == RAW_REASON
    assert first.removals[0].operator_id == api.owner.id
    assert first.removals[0].operator_access_version == 1
    assert first.removals[0].origin.trace_id == "c" * 32
    async with api.uow.sessions.begin() as session:
        session.add(
            PeerFeedbackRemovalRecord(
                id=uuid4(),
                feedback_id=api.revision.id,
                source_version=1,
                operator_id=api.owner.id,
                operator_access_version=1,
                operator_access_active=True,
                kind="abusive",
                reason="  Later retained removal  ",
                removed_at=api.revision.changed_at + timedelta(days=2),
            )
        )
    last = await api.removals()(
        api.owner.credential, api.revision.partner_id, api.revision.id, first.next_cursor
    )
    assert last is not None
    assert tuple(row.id for row in last.removals) == tuple(reversed(identifiers[:3]))
    assert not last.next_cursor
    async with api.uow.sessions() as session:
        after = await source_counts(session)
        assert after[2] == before[2] + 1
        assert after[:2] == before[:2]
        assert after[3:] == before[3:]


async def test_root_current_changed_keyset_filters_and_ordered_pair_unique_real_sources(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine, exchange=False)
    target = api.api.chat.sender
    async with api.uow.sessions() as session:
        subject_id = await session.scalar(select(SubjectRecord.id).limit(1))
        assert isinstance(subject_id, UUID)
    for index in range(OPERATOR_FEEDBACK_PAGE_SIZE + 2):
        sender = await additional_peer(identity_engine, subject_id)
        request = await sent(api.api.chat.api, sender, target)
        accepted = await api.api.chat.api.accept(action(target, sender, request))
        peer = FeedbackServices(
            Chat(sender, target, api.api.chat.api, accepted.conversation.id), api.api.uow
        )
        await peer.outcomes()(peer.outcome())
        result = await peer.feedback()(peer.review())
        async with api.uow.sessions.begin() as session:
            await session.execute(
                update(PeerFeedbackRevisionRecord)
                .where(PeerFeedbackRevisionRecord.feedback_id == result.id)
                .values(changed_at=api.revision.changed_at + timedelta(minutes=index + 1))
            )
    filters = OperatorFeedbackFilters(
        direction=OperatorFeedbackDirection.RECEIVED,
        removed=False,
        changed_from=api.revision.changed_at,
    )
    first = await api.roots()(api.owner.credential, target.id, filters)
    assert first is not None
    assert first.next_cursor is not None
    assert len(first.feedback) == OPERATOR_FEEDBACK_PAGE_SIZE
    assert first.anchor_changed_at is not None
    assert first.anchor_changed_at > first.observed_at
    last = await api.roots()(api.owner.credential, target.id, filters, first.next_cursor)
    assert last is not None
    assert len(last.feedback) == len((1, 2))
    assert not last.next_cursor
    given = await api.roots()(
        api.owner.credential,
        target.id,
        OperatorFeedbackFilters(
            peer_id=api.revision.partner_id,
            direction=OperatorFeedbackDirection.GIVEN,
            changed_before=api.revision.changed_at + timedelta(seconds=1),
        ),
    )
    assert given is not None
    assert tuple(row.id for row in given.feedback) == (api.revision.id,)
    async with api.uow.sessions.begin() as session:
        identifiers = await seed_removals(session, api, 1)
        await session.execute(
            update(PeerFeedbackRecord)
            .where(PeerFeedbackRecord.id == api.revision.id)
            .values(current_removal_id=identifiers[0])
        )
    removed = await api.roots()(
        api.owner.credential, target.id, OperatorFeedbackFilters(removed=True)
    )
    assert removed is not None
    assert tuple(row.id for row in removed.feedback) == (api.revision.id,)
    with pytest.raises(InvalidOperatorCursorError):
        await api.roots()(
            api.owner.credential, target.id, OperatorFeedbackFilters(), first.next_cursor
        )


async def test_no_human_messages_and_max_unicode_note_reason_retained(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine, exchange=False)
    note = "あ" * MAX_OPERATOR_FEEDBACK_TEXT
    reason = "い" * MAX_OPERATOR_FEEDBACK_TEXT
    async with api.uow.sessions.begin() as session:
        await session.execute(
            update(PeerFeedbackRevisionRecord)
            .where(PeerFeedbackRevisionRecord.feedback_id == api.revision.id)
            .values(team_note=note)
        )
        identifiers = await seed_removals(session, api, 1)
        await session.execute(
            update(PeerFeedbackRemovalRecord)
            .where(PeerFeedbackRemovalRecord.id == identifiers[0])
            .values(reason=reason)
        )
    history = await api.history()(api.owner.credential, api.revision.partner_id, api.revision.id)
    assert history is not None
    assert history.revisions[0].team_note == note
    assert history.revisions[0].low_message_id is None
    assert history.revisions[0].high_message_id is None
    removals = await api.removals()(api.owner.credential, api.revision.partner_id, api.revision.id)
    assert removals is not None
    assert removals.removals[0].reason == reason
    assert removals.root.current_removal_id is None


async def test_metadata_sql_never_selects_team_note_private_reason_or_intents(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    statements: list[str] = []

    def capture(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _many: bool,
    ) -> None:
        statements.append(" ".join(statement.lower().split()))

    event.listen(identity_engine.sync_engine, "before_cursor_execute", capture)
    try:
        assert (
            await api.roots()(
                api.owner.credential, api.revision.reviewer_id, OperatorFeedbackFilters()
            )
            is not None
        )
    finally:
        event.remove(identity_engine.sync_engine, "before_cursor_execute", capture)
    sources = [
        sql for sql in statements if sql.startswith("select ") and "from peer_feedback" in sql
    ]
    assert len(sources) == 1
    for private in (
        "team_note",
        "reason",
        "descriptors",
        "again",
        "feedback_command_intents",
        "fingerprint",
    ):
        assert private not in sources[0]
    async with api.uow.sessions() as session:
        with pytest.raises(RuntimeError, match="operator"):
            await SqlOperatorFeedbackTransaction(session, record_operator_audit).feedback_account(
                api.revision.reviewer_id
            )


async def test_foreign_child_and_missing_parent_audits_without_private_data(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    other = await actor(identity_engine)
    missing = uuid4()
    for account, feedback in (
        (other.id, api.revision.id),
        (api.revision.partner_id, missing),
        (missing, api.revision.id),
    ):
        assert await api.history()(api.owner.credential, account, feedback) is None
        assert await api.removals()(api.owner.credential, account, feedback) is None
    async with api.uow.sessions() as session:
        audits = tuple(await session.scalars(select(OperatorAuditRecord)))
        assert all(
            row.outcome == "read" and row.result_ids == [row.requested_id]
            for row in audits
            if row.requested_id != missing
        )
        assert all(
            row.outcome == "not_found" and row.result_ids == []
            for row in audits
            if row.requested_id == missing
        )


@pytest.mark.parametrize("kind", ["roots", "history", "removals"])
async def test_canonical_failure_withholds_every_source_read(
    kind: str, identity_engine: AsyncEngine
) -> None:
    api = await prepared(identity_engine)

    async def fail(session: AsyncSession, audit: OperatorAudit) -> None:
        await record_operator_audit(session, audit)
        raise StorageUnavailableError

    with pytest.raises(StorageUnavailableError):
        await replace(api, uow=replace(api.uow, recorder=fail)).read(kind)
    async with api.uow.sessions() as session:
        assert not tuple(await session.scalars(select(OperatorAuditRecord)))
        assert not tuple(
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind == "operator.inspected")
            )
        )


async def test_final_committed_session_deadline_withholds_raw_feedback(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    async with api.uow.sessions.begin() as session:
        now = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        deadline = now + timedelta(seconds=2)
        await session.execute(
            update(SessionRecord)
            .where(SessionRecord.account_id == api.owner.id)
            .values(expires_at=deadline)
        )
    entered = False

    async def expire(session: AsyncSession, audit: OperatorAudit) -> None:
        nonlocal entered
        await record_operator_audit(session, audit)
        entered = True
        current = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(current, datetime)
        await session.execute(
            select(func.pg_sleep(max(0, (deadline - current).total_seconds()) + 0.05))
        )

    with pytest.raises(UnauthenticatedError):
        await replace(api, uow=replace(api.uow, recorder=expire)).read("history")
    assert entered
    async with api.uow.sessions() as session:
        assert not tuple(await session.scalars(select(OperatorAuditRecord)))


async def test_cancel_and_real_deferred_commit_failure_no_private_result(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    entered, release = asyncio.Event(), asyncio.Event()

    async def paused(session: AsyncSession, audit: OperatorAudit) -> None:
        await record_operator_audit(session, audit)
        entered.set()
        await release.wait()

    task = asyncio.create_task(replace(api, uow=replace(api.uow, recorder=paused)).read("removals"))
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        release.set()
        if not task.done():
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
    staged = False

    async def invalid_commit(session: AsyncSession, audit: OperatorAudit) -> None:
        nonlocal staged
        await record_operator_audit(session, audit)
        await session.execute(
            update(OperatorAccessRecord)
            .where(OperatorAccessRecord.account_id == api.owner.id)
            .values(current_version=2)
        )
        await session.flush()
        staged = True

    with pytest.raises(IntegrityError, match="fk_operator_access_current_revision"):
        await replace(api, uow=replace(api.uow, recorder=invalid_commit)).read("history")
    assert staged
    async with api.uow.sessions() as session:
        assert not tuple(await session.scalars(select(OperatorAuditRecord)))
        assert (
            await session.scalar(
                select(OperatorAccessRecord.current_version).where(
                    OperatorAccessRecord.account_id == api.owner.id
                )
            )
            == 1
        )
    assert await asyncio.wait_for(api.read("history"), timeout=5) is not None
