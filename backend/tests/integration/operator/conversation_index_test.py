"""Actual retained request/conversation sources, explicit operator grant and canonical audit."""

from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from studymate.application.errors import StorageUnavailableError
from studymate.application.operator.conversation_index import ReadOperatorConversations
from studymate.domain.operator.audit import OperatorAudit
from studymate.infrastructure.operator.conversation_index_cursors import (
    FernetOperatorConversationCursorCodec,
)
from studymate.infrastructure.operator.conversation_index_transactions import (
    SqlOperatorConversationIndexUnitOfWork,
)
from studymate.infrastructure.operator.models import OperatorAuditRecord
from studymate.infrastructure.persistence.conversation_models import ConversationRecord
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import record_operator_audit
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.integration.operator.test_reads import operator
from tests.integration.profile_lifecycle_fixture import command, services
from tests.integration.student_actor import actor
from tests.integration.test_message_commands import chat

pytestmark = pytest.mark.integration
CODEC = FernetOperatorConversationCursorCodec.from_key(b"k" * 32)


async def test_both_actual_participants_retain_conversation_metadata_after_hiding_and_deletion(
    identity_engine: AsyncEngine,
) -> None:
    owned = await chat(identity_engine)
    visibility, _ = services(identity_engine)
    await visibility(command(owned.sender))
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    async with sessions.begin() as session:
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == owned.recipient.id)
            .values(deleted_at=func.clock_timestamp())
        )
    owner = await operator(identity_engine)
    read = ReadOperatorConversations(
        SqlOperatorConversationIndexUnitOfWork(sessions, record_operator_audit),
        Sha256SessionHasher(),
        CODEC,
    )
    async with sessions() as session:
        original = await session.get(ConversationRecord, owned.conversation_id)
        assert original is not None
        participants = (original.low_id, original.high_id)
        source_request = original.request_id
        source_version = original.accepted_request_version
    for target in participants:
        page = await read(owner.credential, target)
        assert page is not None
        assert len(page.conversations) == 1
        row = page.conversations[0]
        assert row.id == owned.conversation_id
        assert (row.low_id, row.high_id) == participants
        assert row.request_id == source_request
        assert row.accepted_request_version == source_version
        assert page.next_cursor is None
    async with sessions() as session:
        audits = (
            await session.scalars(
                select(OperatorAuditRecord).where(OperatorAuditRecord.operator_id == owner.id)
            )
        ).all()
        assert {source.requested_id for source in audits} == set(participants)
        for source in audits:
            assert source.action == "read_account"
            canonical = (
                await session.scalars(
                    select(ProductEventRecord).where(
                        ProductEventRecord.operator_audit_id == source.id
                    )
                )
            ).one()
            assert canonical.operator_action == "read_account"


async def rejecting_audit(session: AsyncSession, audit: OperatorAudit) -> None:
    await record_operator_audit(session, audit)
    raise StorageUnavailableError


async def test_missing_and_empty_roots_have_real_audit_while_canonical_failure_rolls_back(
    identity_engine: AsyncEngine,
) -> None:
    owner, empty = await operator(identity_engine), await actor(identity_engine, verified=False)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    read = ReadOperatorConversations(
        SqlOperatorConversationIndexUnitOfWork(sessions, record_operator_audit),
        Sha256SessionHasher(),
        CODEC,
    )
    assert await read(owner.credential, uuid4()) is None
    found = await read(owner.credential, empty.id)
    assert found is not None
    assert not found.conversations
    async with sessions() as session:
        audits = (await session.scalars(select(OperatorAuditRecord))).all()
        assert {row.outcome for row in audits} == {"read", "not_found"}
        before = await session.scalar(select(func.count()).select_from(ProductEventRecord))
    failed = ReadOperatorConversations(
        SqlOperatorConversationIndexUnitOfWork(sessions, rejecting_audit),
        Sha256SessionHasher(),
        CODEC,
    )
    with pytest.raises(StorageUnavailableError):
        await failed(owner.credential, empty.id)
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(ProductEventRecord)) == before
        assert await session.scalar(select(func.count()).select_from(OperatorAuditRecord)) == len(
            audits
        )
