import asyncio
from dataclasses import replace
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from sqlalchemy import func, select, update
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.application.chat_images.start import (
    ChatImageIntent,
    ChatImageMessageResolvedError,
    ChatImageRateLimitedError,
    ChatImageSourceConflictError,
    StartChatImage,
    StartChatImageCommand,
)
from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.messaging.commands import CancelMessageCommand
from studymate.application.messaging.ports import ConversationUnavailableError
from studymate.domain.chat_images import ChatImagePreparation, ChatImageState
from studymate.domain.media import PhotoContentType, PhotoSource
from studymate.infrastructure.chat_images.models import (
    ChatImageAttemptRecord,
    ChatImageIntentRecord,
    ChatImageRecord,
    ChatImageRevisionRecord,
)
from studymate.infrastructure.chat_images.start import (
    SqlChatImageStartTransaction,
    SqlChatImageStartUnitOfWork,
)
from studymate.infrastructure.persistence.conversation_models import ConversationRecord
from studymate.infrastructure.persistence.identity_models import SessionRecord
from studymate.infrastructure.persistence.message_models import MessageOperationRecord
from studymate.infrastructure.persistence.product_events import record_message_outcome
from tests.integration.migrations import run_revision_step
from tests.integration.onboarding_fixture import ready_setup
from tests.integration.profile_lifecycle_fixture import complete_existing_setup
from tests.integration.requests.fixture import FINGERPRINTER, HASHER
from tests.integration.student_actor import actor
from tests.integration.test_message_commands import Chat, chat

pytestmark = pytest.mark.integration
PENDING_LIMIT = 3
BURST = 10
EXPECTED_REPLAY_RECEIPTS = 2


def start(owned: Chat) -> StartChatImage:
    return StartChatImage(
        SqlChatImageStartUnitOfWork(owned.api.sessions, record_message_outcome),
        HASHER,
        FINGERPRINTER,
    )


def submission(owned: Chat) -> StartChatImageCommand:
    return StartChatImageCommand(
        owned.sender.credential,
        owned.conversation_id,
        uuid4(),
        PhotoSource(100, b"p" * 32, PhotoContentType.PNG),
        IntentKey(str(uuid4())),
    )


def revision(image: ChatImagePreparation) -> ChatImageRevisionRecord:
    return ChatImageRevisionRecord(
        image_id=image.id,
        version=image.version,
        account_id=image.account_id,
        conversation_id=image.conversation_id,
        client_message_id=image.client_message_id,
        state=image.state.value,
        updated_at=image.updated_at,
        attempt_id=image.attempt_id,
        ready_attempt_outcome="ready" if image.state == ChatImageState.READY else None,
        failure=image.failure.value if image.failure is not None else None,
    )


async def test_real_admission_replay_binds_source_and_preserves_original_receipt(
    identity_engine: AsyncEngine,
) -> None:
    owned = await chat(identity_engine)
    intent = submission(owned)
    first = await start(owned)(intent)
    assert first.source == intent.source
    queued = first.queue(first.updated_at)
    async with owned.api.sessions.begin() as session:
        session.add(revision(queued))
        await session.flush()
        await session.execute(
            update(ChatImageRecord)
            .where(ChatImageRecord.id == first.id)
            .values(current_version=queued.version)
        )
    assert await start(owned)(intent) == first
    assert await start(owned)(replace(intent, intent_key=IntentKey(str(uuid4())))) == queued
    with pytest.raises(IdempotencyConflictError):
        await start(owned)(replace(intent, source=replace(intent.source, sha256=b"q" * 32)))
    with pytest.raises(ChatImageSourceConflictError):
        await start(owned)(
            replace(
                intent,
                source=replace(intent.source, sha256=b"q" * 32),
                intent_key=IntentKey(str(uuid4())),
            )
        )
    async with owned.api.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(ChatImageRecord)) == 1
        assert (
            await session.scalar(select(func.count()).select_from(ChatImageIntentRecord))
            == EXPECTED_REPLAY_RECEIPTS
        )
        assert await session.scalar(select(func.count()).select_from(MessageOperationRecord)) == 0
        assert await session.scalar(select(ConversationRecord.next_message_sequence)) == 1


async def test_concurrent_starts_enforce_account_capacity_without_spending_message_sequence(
    identity_engine: AsyncEngine,
) -> None:
    owned = await chat(identity_engine)
    outcomes = await asyncio.gather(
        *(start(owned)(submission(owned)) for _ in range(BURST)), return_exceptions=True
    )
    accepted = [item for item in outcomes if isinstance(item, ChatImagePreparation)]
    denied = [item for item in outcomes if isinstance(item, BaseException)]
    assert len(accepted) == PENDING_LIMIT
    assert len(denied) == BURST - PENDING_LIMIT
    assert all(isinstance(item, ChatImageRateLimitedError) for item in denied)
    async with owned.api.sessions() as session:
        assert (
            await session.scalar(select(func.count()).select_from(ChatImageRecord)) == PENDING_LIMIT
        )
        assert (
            await session.scalar(select(func.count()).select_from(ChatImageRevisionRecord))
            == PENDING_LIMIT
        )
        assert await session.scalar(select(func.count()).select_from(MessageOperationRecord)) == 0
        assert await session.scalar(select(ConversationRecord.next_message_sequence)) == 1


@pytest.mark.parametrize("terminal", ["cancelled", "confirmed"])
async def test_terminal_message_blocks_late_image_admission(
    identity_engine: AsyncEngine, terminal: str
) -> None:
    owned = await chat(identity_engine)
    message = owned.command()
    if terminal == "confirmed":
        outcome = await owned.send()(message)
    else:
        outcome = await owned.cancel()(
            CancelMessageCommand(
                message.credential,
                message.conversation_id,
                message.client_message_id,
                IntentKey(str(uuid4())),
            )
        )
    intent = replace(submission(owned), client_message_id=message.client_message_id)
    with pytest.raises(ChatImageMessageResolvedError) as error:
        await start(owned)(intent)
    assert error.value.operation == outcome
    async with owned.api.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(ChatImageRecord)) == 0


async def test_foreign_and_missing_conversation_do_not_admit_or_leak_image_source(
    identity_engine: AsyncEngine,
) -> None:
    owned = await chat(identity_engine)
    foreign = await actor(identity_engine)
    await ready_setup(identity_engine, foreign.credential)
    await complete_existing_setup(identity_engine, foreign)
    original = submission(owned)
    for intent in (
        replace(original, conversation_id=uuid4()),
        replace(original, credential=foreign.credential),
    ):
        with pytest.raises(ConversationUnavailableError):
            await start(owned)(intent)
    async with owned.api.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(ChatImageRecord)) == 0


@pytest.mark.parametrize("failure", ["expiry", "persistence"])
async def test_admission_failure_rolls_back_source_revision_and_receipt(
    identity_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    owned = await chat(identity_engine)
    original_now = SqlChatImageStartTransaction.now
    original_remember = SqlChatImageStartTransaction.remember_image_start
    written = False

    async def remember(
        transaction: SqlChatImageStartTransaction,
        actor_id: UUID,
        key: IntentKey,
        intent: ChatImageIntent,
        at: datetime,
    ) -> None:
        nonlocal written
        await original_remember(transaction, actor_id, key, intent, at)
        written = True
        if failure == "persistence":
            raise RuntimeError("controlled post-write persistence failure")

    async def clock(transaction: SqlChatImageStartTransaction) -> datetime:
        if written:
            expiry = await transaction.session.scalar(
                select(SessionRecord.expires_at).where(SessionRecord.account_id == owned.sender.id)
            )
            assert expiry is not None
            return expiry
        return await original_now(transaction)

    monkeypatch.setattr(SqlChatImageStartTransaction, "remember_image_start", remember)
    monkeypatch.setattr(SqlChatImageStartTransaction, "now", clock)
    expected = UnauthenticatedError if failure == "expiry" else RuntimeError
    with pytest.raises(expected):
        await start(owned)(submission(owned))
    async with owned.api.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(ChatImageRecord)) == 0
        assert await session.scalar(select(func.count()).select_from(ChatImageRevisionRecord)) == 0
        assert await session.scalar(select(func.count()).select_from(ChatImageIntentRecord)) == 0


@pytest.mark.parametrize("invalid", ["ready_without_attempt", "unknown_attempt", "unready_attempt"])
async def test_database_refuses_fabricated_ready_image_source(
    identity_engine: AsyncEngine,
    invalid: str,
) -> None:
    owned = await chat(identity_engine)
    image = await start(owned)(submission(owned))

    async def violate() -> None:
        async with owned.api.sessions.begin() as session:
            attempt_id = uuid4() if invalid != "ready_without_attempt" else None
            if invalid == "unready_attempt":
                session.add(
                    ChatImageAttemptRecord(
                        id=attempt_id,
                        image_id=image.id,
                        number=1,
                        started_at=image.created_at,
                        lease_until=image.created_at + timedelta(minutes=2),
                        outcome="processing",
                    )
                )
                await session.flush()
            await session.execute(
                update(ChatImageRevisionRecord)
                .where(ChatImageRevisionRecord.image_id == image.id)
                .values(state="ready", attempt_id=attempt_id, ready_attempt_outcome="ready")
            )

    with pytest.raises(IntegrityError):
        await violate()
    async with owned.api.sessions() as session:
        assert await session.scalar(select(ChatImageRevisionRecord.state)) == "uploading"


async def test_real_full_chain_refuses_to_drop_retained_image_preparation(
    identity_engine: AsyncEngine,
) -> None:
    owned = await chat(identity_engine)
    image = await start(owned)(submission(owned))

    def downgrade(connection: Connection) -> None:
        config = Config("alembic.ini")
        config.attributes["connection"] = connection
        alembic_command.downgrade(config, "0040_operator_reports")

    with pytest.raises(RuntimeError, match="Refusing to drop retained chat image preparations"):
        async with identity_engine.begin() as connection:
            await connection.run_sync(
                run_revision_step, "0041_chat_image_preparations", "downgrade"
            )
    with pytest.raises(
        RuntimeError, match="Refusing to drop retained chat image transport cleanup metadata"
    ):
        async with identity_engine.begin() as connection:
            await connection.run_sync(run_revision_step, "0048_chat_image_cleanup", "downgrade")
    with pytest.raises(RuntimeError, match="retained observations or external delivery facts"):
        async with identity_engine.begin() as connection:
            await connection.run_sync(downgrade)
    assert (
        await start(owned)(replace(submission(owned), client_message_id=image.client_message_id))
        == image
    )


@pytest.mark.parametrize(
    "processing", [False, True], ids=["upload-deadline", "processing-deadline"]
)
async def test_expired_preparations_release_capacity_but_retain_every_source_and_attempt(
    identity_engine: AsyncEngine,
    processing: bool,
) -> None:
    owned = await chat(identity_engine)
    async with owned.api.sessions.begin() as session:
        now = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        conversation = await session.get(ConversationRecord, owned.conversation_id)
        assert conversation is not None
        # Controlled retained preparations with elapsed deadlines, not invented sends.
        for _ in range(PENDING_LIMIT):
            image_id, client_id = uuid4(), uuid4()
            created = now - timedelta(minutes=20)
            image = ChatImagePreparation(
                image_id,
                owned.sender.id,
                owned.conversation_id,
                client_id,
                PhotoSource(100, b"p" * 32, PhotoContentType.PNG),
                created,
                created + timedelta(minutes=5),
                created + timedelta(minutes=15),
                created,
            )
            session.add(
                ChatImageRecord(
                    id=image_id,
                    account_id=image.account_id,
                    conversation_id=image.conversation_id,
                    low_id=conversation.low_id,
                    high_id=conversation.high_id,
                    client_message_id=client_id,
                    current_version=2 if processing else 1,
                    source_size=image.source.size,
                    source_digest=image.source.sha256,
                    content_type=image.source.content_type.value,
                    created_at=created,
                    upload_expires_at=image.upload_expires_at,
                    processing_expires_at=image.processing_expires_at,
                )
            )
            await session.flush()
            session.add(revision(image))
            if processing:
                attempt_id = uuid4()
                session.add(
                    ChatImageAttemptRecord(
                        id=attempt_id,
                        image_id=image_id,
                        number=1,
                        started_at=created + timedelta(minutes=10),
                        lease_until=created + timedelta(minutes=12),
                        outcome="processing",
                    )
                )
                await session.flush()
                image = replace(
                    image,
                    version=2,
                    state=ChatImageState.PROCESSING,
                    attempt_id=attempt_id,
                    updated_at=created + timedelta(minutes=10),
                )
                session.add(revision(image))
            await session.flush()
    admitted = await start(owned)(submission(owned))
    assert admitted.state == ChatImageState.UPLOADING
    async with owned.api.sessions() as session:
        assert (
            await session.scalar(select(func.count()).select_from(ChatImageRecord))
            == PENDING_LIMIT + 1
        )
        expired = tuple(
            await session.scalars(
                select(ChatImageRevisionRecord)
                .join(
                    ChatImageRecord,
                    (ChatImageRecord.id == ChatImageRevisionRecord.image_id)
                    & (ChatImageRecord.current_version == ChatImageRevisionRecord.version),
                )
                .where(ChatImageRevisionRecord.state == "expired")
            )
        )
        assert len(expired) == PENDING_LIMIT
        if processing:
            attempts = tuple(await session.scalars(select(ChatImageAttemptRecord)))
            assert len(attempts) == PENDING_LIMIT
            assert all(attempt.outcome == "interrupted" for attempt in attempts)
            assert all(attempt.finished_at is not None for attempt in attempts)
        assert await session.scalar(select(func.count()).select_from(MessageOperationRecord)) == 0
