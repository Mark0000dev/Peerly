"""Actual retained chat source joins and canonical0056 audit; no real object service."""

from dataclasses import dataclass, replace
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from studymate.application.errors import StorageUnavailableError
from studymate.application.operator.chat_media import ReadOperatorChatMedia
from studymate.domain.operator.audit import OperatorAudit, OperatorAuditOutcome
from studymate.domain.operator.chat_media import OperatorChatMediaKind, OperatorChatMediaRequest
from studymate.infrastructure.chat_images.models import ChatImageAttemptRecord
from studymate.infrastructure.operator.chat_media_transactions import SqlOperatorChatMediaUnitOfWork
from studymate.infrastructure.operator.models import OperatorAuditRecord
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.product_events import record_operator_audit
from tests.integration.operator.test_chat_image_metadata import Images, prepared
from tests.integration.operator.test_media_read import RetainedReader
from tests.integration.requests.fixture import HASHER

pytestmark = pytest.mark.integration
PRIVATE_CHAT_BYTES = b"synthetic-private-chat-object"


@dataclass(frozen=True, slots=True)
class ChatMedia:
    images: Images
    request: OperatorChatMediaRequest
    reader: RetainedReader

    def read(self) -> ReadOperatorChatMedia:
        return ReadOperatorChatMedia(
            SqlOperatorChatMediaUnitOfWork(self.images.chat.api.sessions, record_operator_audit),
            HASHER,
            self.reader,
        )


async def chat_media(engine: AsyncEngine) -> ChatMedia:
    images = await prepared(engine)
    attempt_id = uuid4()
    async with images.chat.api.sessions.begin() as session:
        at = images.image.created_at
        session.add(
            ChatImageAttemptRecord(
                id=attempt_id,
                image_id=images.image.id,
                number=1,
                started_at=at,
                lease_until=at + timedelta(seconds=30),
                finished_at=at,
                next_attempt_at=None,
                outcome="stale",
                failure=None,
                display_width=None,
                display_height=None,
                display_size=None,
                display_digest=None,
            )
        )
    request = OperatorChatMediaRequest(
        images.image.account_id, images.image.id, attempt_id, OperatorChatMediaKind.ORIGINAL
    )
    reader = RetainedReader(
        engine,
        {
            replace(request, kind=kind).reference: PRIVATE_CHAT_BYTES
            for kind in OperatorChatMediaKind
        },
    )
    return ChatMedia(images, request, reader)


@pytest.mark.parametrize("kind", list(OperatorChatMediaKind))
async def test_deleted_banned_owner_and_nonready_attempt_are_privileged_retained_sources(
    identity_engine: AsyncEngine,
    kind: OperatorChatMediaKind,
) -> None:
    media = await chat_media(identity_engine)
    async with media.images.chat.api.sessions.begin() as session:
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == media.request.account_id)
            .values(deleted_at=func.clock_timestamp(), banned_at=func.clock_timestamp())
        )
    result = await media.read()(media.images.owner.credential, replace(media.request, kind=kind))
    assert result is not None
    assert result.data == PRIVATE_CHAT_BYTES
    async with media.images.chat.api.sessions() as session:
        audit = (await session.scalars(select(OperatorAuditRecord))).one()
        assert audit.action == "read_chat_media"
        assert audit.resource_kind == "chat_media"
        assert audit.requested_id == media.request.image_id
        assert audit.result_ids == [media.request.image_id]
        assert audit.actual_source_upload_id is None
        assert audit.actual_source_image_id == media.request.image_id


@pytest.mark.parametrize("missing", ["owner", "attempt", "image", "object"])
async def test_exact_missing_source_or_object_is_audited_without_cross_source_fallback(
    identity_engine: AsyncEngine,
    missing: str,
) -> None:
    media = await chat_media(identity_engine)
    request = media.request
    if missing == "owner":
        request = replace(request, account_id=media.images.owner.id)
    elif missing == "attempt":
        request = replace(request, attempt_id=uuid4())
    elif missing == "image":
        request = replace(request, image_id=uuid4())
    else:
        media.reader.objects.clear()
    assert await media.read()(media.images.owner.credential, request) is None
    assert bool(media.reader.references) == (missing == "object")
    async with media.images.chat.api.sessions() as session:
        audit = (await session.scalars(select(OperatorAuditRecord))).one()
        assert audit.outcome == OperatorAuditOutcome.NOT_FOUND.value
        assert audit.requested_id == request.image_id
        assert audit.result_ids == []
        assert audit.actual_source_image_id == (request.image_id if missing == "object" else None)
        assert audit.actual_source_upload_id is None


async def fail_chat_audit(session: AsyncSession, audit: OperatorAudit) -> None:
    await record_operator_audit(session, audit)
    raise StorageUnavailableError


async def test_canonical_audit_failure_rolls_back_and_releases_no_chat_bytes(
    identity_engine: AsyncEngine,
) -> None:
    media = await chat_media(identity_engine)
    usecase = ReadOperatorChatMedia(
        SqlOperatorChatMediaUnitOfWork(media.images.chat.api.sessions, fail_chat_audit),
        HASHER,
        media.reader,
    )
    with pytest.raises(StorageUnavailableError):
        await usecase(media.images.owner.credential, media.request)
    async with media.images.chat.api.sessions() as session:
        assert tuple(await session.scalars(select(OperatorAuditRecord))) == ()
