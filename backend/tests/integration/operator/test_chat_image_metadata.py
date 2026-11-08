"""Real retained chat-image sources; no processor/storage/provider or current participant policy."""

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
from studymate.application.operator.chat_image_ports import OperatorChatImageFilters
from studymate.application.operator.chat_image_uploads import (
    ReadOperatorChatImageHistory,
    ReadOperatorChatImageUploads,
)
from studymate.application.operator.cursors import InvalidOperatorCursorError
from studymate.domain.chat_images import ChatImagePreparation, ChatImageState
from studymate.domain.messaging import MessageOutcome
from studymate.domain.operator.audit import OperatorAudit
from studymate.domain.operator.chat_image_uploads import OPERATOR_CHAT_IMAGE_PAGE_SIZE
from studymate.infrastructure.chat_images.models import (
    ChatImageAttemptRecord,
    ChatImageIntentRecord,
    ChatImageRecord,
    ChatImageRevisionRecord,
)
from studymate.infrastructure.operator.chat_image_cursors import FernetOperatorChatImageCursorCodec
from studymate.infrastructure.operator.chat_image_transactions import (
    SqlOperatorChatImageTransaction,
    SqlOperatorChatImageUnitOfWork,
)
from studymate.infrastructure.operator.models import OperatorAccessRecord, OperatorAuditRecord
from studymate.infrastructure.persistence.identity_models import AccountRecord, SessionRecord
from studymate.infrastructure.persistence.message_models import (
    MessageCommandIntentRecord,
    MessageOperationRecord,
    MessageRecord,
)
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import record_operator_audit
from tests.integration.chat_images.legacy import seed_legacy_text_outcome
from tests.integration.operator.test_reads import operator
from tests.integration.requests.fixture import FINGERPRINTER, HASHER
from tests.integration.student_actor import Actor, actor
from tests.integration.test_chat_image_start import start, submission
from tests.integration.test_message_commands import Chat, chat

pytestmark = pytest.mark.integration
HIGHEST_RETAINED_VERSION = 99
REJECTED_VERSION = 2
CODEC = FernetOperatorChatImageCursorCodec.from_key(b"i" * 32)


@dataclass(frozen=True, slots=True)
class Images:
    chat: Chat
    image: ChatImagePreparation
    owner: Actor
    uow: SqlOperatorChatImageUnitOfWork

    def roots(self) -> ReadOperatorChatImageUploads:
        return ReadOperatorChatImageUploads(self.uow, HASHER, FINGERPRINTER, CODEC)

    def history(self) -> ReadOperatorChatImageHistory:
        return ReadOperatorChatImageHistory(self.uow, HASHER, CODEC)


async def prepared(engine: AsyncEngine) -> Images:
    owned = await chat(engine)
    image = await start(owned)(submission(owned))
    return Images(
        owned,
        image,
        await operator(engine),
        SqlOperatorChatImageUnitOfWork(
            owned.api.sessions,
            record_operator_audit,
        ),
    )


def retained_revision(api: Images, version: int) -> ChatImageRevisionRecord:
    return ChatImageRevisionRecord(
        image_id=api.image.id,
        version=version,
        account_id=api.image.account_id,
        conversation_id=api.image.conversation_id,
        client_message_id=api.image.client_message_id,
        state="rejected" if version == REJECTED_VERSION else "expired",
        updated_at=api.image.created_at - timedelta(minutes=version),
        attempt_id=None,
        ready_attempt_outcome=None,
        failure="invalid_image" if version == REJECTED_VERSION else None,
    )


async def seed_root(session: AsyncSession, api: Images, at: datetime) -> UUID:
    source = await session.get(ChatImageRecord, api.image.id)
    assert source is not None
    identifier, client_id = uuid4(), uuid4()
    session.add(
        ChatImageRecord(
            id=identifier,
            account_id=source.account_id,
            conversation_id=source.conversation_id,
            low_id=source.low_id,
            high_id=source.high_id,
            client_message_id=client_id,
            current_version=1,
            source_size=source.source_size,
            source_digest=source.source_digest,
            content_type=source.content_type,
            created_at=at,
            upload_expires_at=at + timedelta(minutes=5),
            processing_expires_at=at + timedelta(minutes=10),
        )
    )
    await session.flush()
    session.add(
        ChatImageRevisionRecord(
            image_id=identifier,
            version=1,
            account_id=source.account_id,
            conversation_id=source.conversation_id,
            client_message_id=client_id,
            state="expired",
            updated_at=at,
            attempt_id=None,
            ready_attempt_outcome=None,
            failure=None,
        )
    )
    await session.flush()
    return identifier


async def source_counts(session: AsyncSession) -> tuple[int, ...]:
    values = []
    for model in (
        ChatImageRecord,
        ChatImageRevisionRecord,
        ChatImageAttemptRecord,
        ChatImageIntentRecord,
        MessageRecord,
        MessageOperationRecord,
        MessageCommandIntentRecord,
    ):
        value = await session.scalar(select(func.count()).select_from(model))
        assert value is not None
        values.append(value)
    return tuple(values)


async def test_history_all_versions_current_attempts_retained_owner_and_no_attachment_proof(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    text = await seed_legacy_text_outcome(api.chat, api.image)
    assert text.message is not None
    async with api.uow.sessions.begin() as session:
        for version in range(2, OPERATOR_CHAT_IMAGE_PAGE_SIZE + 4):
            session.add(retained_revision(api, version))
        for number, outcome in ((1, "ready"), (2, "retry"), (3, "rejected")):
            session.add(
                ChatImageAttemptRecord(
                    id=UUID(int=6000 + number),
                    image_id=api.image.id,
                    number=number,
                    started_at=api.image.created_at,
                    lease_until=api.image.created_at + timedelta(seconds=30),
                    finished_at=api.image.created_at + timedelta(seconds=1),
                    next_attempt_at=api.image.created_at + timedelta(seconds=2)
                    if outcome == "retry"
                    else None,
                    outcome=outcome,
                    failure="invalid_image" if outcome == "rejected" else None,
                    display_width=10 if outcome == "ready" else None,
                    display_height=10 if outcome == "ready" else None,
                    display_size=100 if outcome == "ready" else None,
                    display_digest=b"d" * 32 if outcome == "ready" else None,
                )
            )
        await session.flush()
        ready = retained_revision(api, HIGHEST_RETAINED_VERSION)
        ready.state, ready.attempt_id, ready.ready_attempt_outcome = (
            "ready",
            UUID(int=6001),
            "ready",
        )
        session.add(ready)
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == api.image.account_id)
            .values(banned_at=api.image.created_at, deleted_at=api.image.created_at)
        )
        before = await source_counts(session)
    first = await api.history()(api.owner.credential, api.image.account_id, api.image.id)
    assert first is not None
    assert first.anchor_version == HIGHEST_RETAINED_VERSION
    assert first.upload.current_version == 1
    assert first.revisions[0].state == ChatImageState.READY
    assert first.revisions[0].ready_attempt_outcome is not None
    assert first.revisions[0].ready_attempt_outcome.value == "ready"
    assert first.next_cursor is not None
    assert len(first.revisions) == OPERATOR_CHAT_IMAGE_PAGE_SIZE
    assert len(first.attempts_current) == len((1, 2, 3))
    assert first.attempts_current[0].display_sha256 == b"d" * 32
    assert first.matching_client_operation is not None
    assert first.matching_client_operation.id == text.id
    assert first.matching_client_operation.state == MessageOutcome.CONFIRMED
    assert first.matching_client_operation.message_id == text.message.id
    second = await api.history()(
        api.owner.credential, api.image.account_id, api.image.id, first.next_cursor
    )
    assert second is not None
    assert tuple(row.version for row in second.revisions) == (4, 3, 2, 1)
    assert not second.next_cursor
    assert first.upload.source_sha256 == api.image.source.sha256
    assert api.image.source.sha256.hex() not in repr(first)
    async with api.uow.sessions() as session:
        assert await source_counts(session) == before
        assert await session.scalar(select(ChatImageRecord.current_version)) == 1
        audits = tuple(await session.scalars(select(OperatorAuditRecord)))
        assert len(audits) == len((first, second))
        assert all(
            row.action == "read_account" and row.result_ids == [api.image.account_id]
            for row in audits
        )
        events = tuple(
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind == "operator.inspected")
            )
        )
        assert len(events) == len(audits)


async def test_root_filters_metadata_anchor_and_wrong_query_cursor(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    async with api.uow.sessions.begin() as session:
        for index in range(OPERATOR_CHAT_IMAGE_PAGE_SIZE + 2):
            await seed_root(session, api, api.image.created_at + timedelta(minutes=index + 1))
    filters = OperatorChatImageFilters(
        conversation_id=api.image.conversation_id,
        state=ChatImageState.EXPIRED,
        created_from=api.image.created_at,
    )
    first = await api.roots()(api.owner.credential, api.image.account_id, filters)
    assert first is not None
    assert first.next_cursor is not None
    assert len(first.uploads) == OPERATOR_CHAT_IMAGE_PAGE_SIZE
    assert first.anchor_created_at is not None
    assert first.anchor_created_at > first.observed_at
    async with api.uow.sessions.begin() as session:
        await seed_root(session, api, api.image.created_at + timedelta(days=2))
    last = await api.roots()(api.owner.credential, api.image.account_id, filters, first.next_cursor)
    assert last is not None
    assert len(last.uploads) == len((1, 2))
    assert not last.next_cursor
    for query in (
        OperatorChatImageFilters(conversation_id=uuid4()),
        OperatorChatImageFilters(state=ChatImageState.READY),
        OperatorChatImageFilters(created_before=api.image.created_at),
    ):
        empty = await api.roots()(api.owner.credential, api.image.account_id, query)
        assert empty is not None
        assert not empty.uploads
    with pytest.raises(InvalidOperatorCursorError):
        await api.roots()(
            api.owner.credential,
            api.image.account_id,
            OperatorChatImageFilters(),
            first.next_cursor,
        )


async def test_other_participant_not_upload_owner_missing_parent_and_child_audits(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    unknown = await actor(identity_engine)
    missing = uuid4()
    for account, image in (
        (api.chat.recipient.id, api.image.id),
        (api.image.account_id, missing),
        (unknown.id, api.image.id),
        (missing, api.image.id),
    ):
        assert await api.history()(api.owner.credential, account, image) is None
    empty = await api.roots()(
        api.owner.credential, api.chat.recipient.id, OperatorChatImageFilters()
    )
    assert empty is not None
    assert not empty.uploads
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


async def test_actual_message_match_excludes_same_client_other_author(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    other = await api.chat.send()(
        replace(api.chat.command(api.chat.recipient), client_message_id=api.image.client_message_id)
    )
    assert other.author_id != api.image.account_id
    page = await api.history()(api.owner.credential, api.image.account_id, api.image.id)
    assert page is not None
    assert page.matching_client_operation is None
    async with api.uow.sessions() as session:
        assert (await session.scalars(select(MessageOperationRecord))).one().id == other.id


async def test_sql_sources_exclude_intents_message_body_and_require_operator(
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
                api.owner.credential, api.image.account_id, OperatorChatImageFilters()
            )
            is not None
        )
        assert (
            await api.history()(api.owner.credential, api.image.account_id, api.image.id)
            is not None
        )
    finally:
        event.remove(identity_engine.sync_engine, "before_cursor_execute", capture)
    sources = [
        sql
        for sql in statements
        if sql.startswith("select ")
        and ("from chat_image" in sql or "from message_operations" in sql)
    ]
    assert sources
    for source in sources:
        for forbidden in (
            "chat_image_intents",
            "message_command_intents",
            "messages.text",
            "storage_key",
            "fingerprint",
        ):
            assert forbidden not in source
    async with api.uow.sessions() as session:
        with pytest.raises(RuntimeError, match="operator"):
            await SqlOperatorChatImageTransaction(
                session, record_operator_audit
            ).chat_image_account(api.image.account_id)


@pytest.mark.parametrize("read_history", [True, False])
async def test_actual_canonical_failure_rolls_back_before_data(
    read_history: bool, identity_engine: AsyncEngine
) -> None:
    api = await prepared(identity_engine)

    async def fail(session: AsyncSession, audit: OperatorAudit) -> None:
        await record_operator_audit(session, audit)
        raise StorageUnavailableError

    broken = replace(api, uow=replace(api.uow, recorder=fail))
    call = (
        broken.history()(api.owner.credential, api.image.account_id, api.image.id)
        if read_history
        else broken.roots()(api.owner.credential, api.image.account_id, OperatorChatImageFilters())
    )
    with pytest.raises(StorageUnavailableError):
        await call
    async with api.uow.sessions() as session:
        assert not tuple(await session.scalars(select(OperatorAuditRecord)))
        assert not tuple(
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind == "operator.inspected")
            )
        )


async def test_final_committed_session_deadline_withholds_history(
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

    broken = replace(api, uow=replace(api.uow, recorder=expire))
    with pytest.raises(UnauthenticatedError):
        await broken.history()(api.owner.credential, api.image.account_id, api.image.id)
    assert entered
    async with api.uow.sessions() as session:
        assert not tuple(await session.scalars(select(OperatorAuditRecord)))


async def test_cancellation_releases_privilege_locks_and_rolls_back(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    entered, release = asyncio.Event(), asyncio.Event()

    async def paused(session: AsyncSession, audit: OperatorAudit) -> None:
        await record_operator_audit(session, audit)
        entered.set()
        await release.wait()

    broken = replace(api, uow=replace(api.uow, recorder=paused))
    task = asyncio.create_task(
        broken.history()(api.owner.credential, api.image.account_id, api.image.id)
    )
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
    async with api.uow.sessions() as session:
        assert not tuple(await session.scalars(select(OperatorAuditRecord)))
    assert (
        await asyncio.wait_for(
            api.history()(api.owner.credential, api.image.account_id, api.image.id), timeout=5
        )
        is not None
    )


async def test_real_deferred_commit_failure_returns_no_history(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
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

    broken = replace(api, uow=replace(api.uow, recorder=invalid_commit))
    with pytest.raises(IntegrityError, match="fk_operator_access_current_revision"):
        await broken.history()(api.owner.credential, api.image.account_id, api.image.id)
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
    assert await api.history()(api.owner.credential, api.image.account_id, api.image.id) is not None
