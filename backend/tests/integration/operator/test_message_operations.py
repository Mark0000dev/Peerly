from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.application.idempotency import IntentKey
from studymate.application.messaging.commands import CancelMessageCommand
from studymate.application.operator.message_operations import (
    ReadOperatorMessageOperation,
    ReadOperatorMessageOperations,
)
from studymate.infrastructure.operator.message_operations_cursors import (
    FernetOperatorMessageOperationCursorCodec,
)
from studymate.infrastructure.operator.message_operations_transactions import (
    SqlOperatorMessageOperationsUnitOfWork,
)
from studymate.infrastructure.operator.models import OperatorAuditRecord
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.product_events import record_operator_audit
from tests.integration.operator.test_reads import operator
from tests.integration.requests.fixture import HASHER
from tests.integration.test_message_commands import chat

pytestmark = pytest.mark.integration


async def test_real_confirmed_cancelled_and_author_scope_retained_after_deletion(
    identity_engine: AsyncEngine,
) -> None:
    context = await chat(identity_engine)
    confirmed = await context.send()(context.command())
    cancelled = await context.cancel()(
        CancelMessageCommand(
            context.sender.credential,
            context.conversation_id,
            uuid4(),
            IntentKey("cancel-inspection"),
        )
    )
    viewer = await operator(identity_engine)
    unit = SqlOperatorMessageOperationsUnitOfWork(context.api.sessions, record_operator_audit)
    read = ReadOperatorMessageOperations(
        unit, HASHER, FernetOperatorMessageOperationCursorCodec.from_key(b"m" * 32)
    )
    detail = ReadOperatorMessageOperation(unit, HASHER)
    async with context.api.sessions.begin() as session:
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == context.sender.id)
            .values(deleted_at=func.clock_timestamp())
        )
    page = await read(viewer.credential, context.sender.id)
    assert page is not None
    assert {row.id for row in page.operations} == {confirmed.id, cancelled.id}
    actual = await detail(viewer.credential, context.sender.id, confirmed.id)
    assert actual is not None
    assert actual.message is not None
    assert confirmed.message is not None
    assert actual.message.id == confirmed.message.id
    assert actual.message.text == confirmed.message.content.text
    assert actual.terminal_at == confirmed.message.sent_at
    terminal = await detail(viewer.credential, context.sender.id, cancelled.id)
    assert terminal is not None
    assert terminal.message is None
    assert terminal.terminal_at == cancelled.cancelled_at
    assert await detail(viewer.credential, context.recipient.id, confirmed.id) is None
    async with context.api.sessions() as session:
        foreign = (
            await session.scalars(
                select(OperatorAuditRecord).where(
                    OperatorAuditRecord.requested_id == context.recipient.id
                )
            )
        ).one()
        assert foreign.outcome == "read"
        assert foreign.result_ids == [context.recipient.id]


async def test_real_operation_keyset_is_bounded_and_skips_newer_terminal_sources(
    identity_engine: AsyncEngine,
) -> None:
    context = await chat(identity_engine)
    viewer = await operator(identity_engine)
    for _ in range(51):
        await context.cancel()(
            CancelMessageCommand(
                context.sender.credential, context.conversation_id, uuid4(), IntentKey(str(uuid4()))
            )
        )
    read = ReadOperatorMessageOperations(
        SqlOperatorMessageOperationsUnitOfWork(context.api.sessions, record_operator_audit),
        HASHER,
        FernetOperatorMessageOperationCursorCodec.from_key(b"m" * 32),
    )
    first = await read(viewer.credential, context.sender.id)
    assert first is not None
    assert first.next_cursor is not None
    newer = await context.cancel()(
        CancelMessageCommand(
            context.sender.credential, context.conversation_id, uuid4(), IntentKey(str(uuid4()))
        )
    )
    second = await read(viewer.credential, context.sender.id, first.next_cursor)
    assert second is not None
    assert len(second.operations) == 1
    assert second.next_cursor is None
    assert newer.id not in {row.id for row in (*first.operations, *second.operations)}
