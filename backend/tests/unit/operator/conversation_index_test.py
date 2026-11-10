from dataclasses import replace
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from studymate.application.errors import StorageUnavailableError
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.operator.authority import OperatorAccessDeniedError
from studymate.application.operator.conversation_index import ReadOperatorConversations
from studymate.application.operator.conversation_index_ports import OperatorConversationPosition
from studymate.application.operator.cursors import InvalidOperatorCursorError, OperatorCursorScope
from studymate.domain.operator.audit import OperatorAudit, OperatorAuditOutcome
from studymate.domain.operator.conversation_index import (
    OPERATOR_CONVERSATION_PAGE_SIZE,
    OperatorConversationSummary,
)
from studymate.infrastructure.operator.conversation_index_cursors import (
    FernetOperatorConversationCursorCodec,
)
from studymate.infrastructure.operator.conversation_index_transactions import (
    SqlOperatorConversationIndexTransaction,
)
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.unit.identity_store import CREDENTIAL
from tests.unit.operator.conversation_index_store import ConversationIndexStore
from tests.unit.operator.store import TARGET

if TYPE_CHECKING:
    from collections.abc import Awaitable

CODEC = FernetOperatorConversationCursorCodec.from_key(b"k" * 32)


def summary(index: int) -> OperatorConversationSummary:
    return OperatorConversationSummary(
        UUID(int=index + 1), uuid4(), TARGET, UUID(int=1000), uuid4(), 2
    )


def reader(store: ConversationIndexStore) -> ReadOperatorConversations:
    return ReadOperatorConversations(store, Sha256SessionHasher(), CODEC)


async def test_bounded_uuid_keyset_lists_only_actual_participant_and_audits_account_container() -> (
    None
):
    store = ConversationIndexStore()
    store.assign_explicit_operator()
    store.rows = tuple(summary(index) for index in range(OPERATOR_CONVERSATION_PAGE_SIZE + 1))
    first = await reader(store)(CREDENTIAL, TARGET)
    assert first is not None
    assert len(first.conversations) == OPERATOR_CONVERSATION_PAGE_SIZE
    assert first.next_cursor is not None
    second = await reader(store)(CREDENTIAL, TARGET, first.next_cursor)
    assert second is not None
    assert second.conversations == (store.rows[0],)
    assert second.next_cursor is None
    assert store.audit[-1].requested is not None
    assert store.audit[-1].requested.id == TARGET
    assert store.audit[-1].results == (store.audit[-1].requested,)
    assert store.audit[-1].outcome == OperatorAuditOutcome.READ


async def test_missing_root_is_audited_not_found_and_empty_existing_root_is_read() -> None:
    store = ConversationIndexStore()
    store.assign_explicit_operator()
    missing = await reader(store)(CREDENTIAL, uuid4())
    assert missing is None
    missing_audit = store.audit[-1]
    assert missing_audit.outcome == OperatorAuditOutcome.NOT_FOUND
    assert missing_audit.results == ()
    empty = await reader(store)(CREDENTIAL, TARGET)
    assert empty is not None
    assert not empty.conversations
    assert empty.next_cursor is None
    assert store.audit[-1].outcome == OperatorAuditOutcome.READ


def test_cursor_is_bound_to_actual_operator_grant_target_and_purpose() -> None:
    scope = OperatorCursorScope(uuid4(), 1)
    position = OperatorConversationPosition(uuid4())
    token = CODEC.encode_conversations(scope, TARGET, position)
    assert CODEC.decode_conversations(scope, TARGET, token) == position
    for actor, target in (
        (replace(scope, account_id=uuid4()), TARGET),
        (replace(scope, access_version=2), TARGET),
        (scope, uuid4()),
    ):
        with pytest.raises(InvalidOperatorCursorError):
            CODEC.decode_conversations(actor, target, token)
    with pytest.raises(InvalidOperatorCursorError):
        CODEC.decode_conversations(scope, TARGET, "invalid")
    with pytest.raises(ValueError, match="32-byte"):
        FernetOperatorConversationCursorCodec.from_key(b"bad")


@pytest.mark.parametrize("fault", ["foreign", "order", "too_many"])
async def test_broken_sources_cannot_escape_as_conversation_metadata(fault: str) -> None:
    store = ConversationIndexStore()
    store.assign_explicit_operator()
    if fault == "foreign":
        store.override_rows = (replace(summary(0), low_id=UUID(int=11)),)
    elif fault == "order":
        store.override_rows = (summary(0), summary(1))
    else:
        store.override_rows = tuple(
            summary(index) for index in range(OPERATOR_CONVERSATION_PAGE_SIZE + 2)
        )
    with pytest.raises(RuntimeError, match=r"participant|bounded"):
        await reader(store)(CREDENTIAL, TARGET)
    assert not store.audit


@pytest.mark.parametrize("fault", ["ordinary", "revoked", "banned"])
async def test_actual_role_required_before_any_target_source_read(fault: str) -> None:
    store = ConversationIndexStore()
    if fault != "ordinary":
        store.assign_explicit_operator()
    if fault == "revoked":
        assert store.access is not None
        store.access = replace(store.access, active=False)
    elif fault == "banned":
        store.actor = replace(store.actor, banned=True)
    with pytest.raises(OperatorAccessDeniedError):
        await reader(store)(CREDENTIAL, TARGET)
    assert store.private_queries == 0
    assert not store.audit


@pytest.mark.parametrize("fault", ["audit", "expired"])
async def test_audit_or_final_session_failure_rolls_back_and_prevents_return(fault: str) -> None:
    store = ConversationIndexStore()
    store.assign_explicit_operator()
    store.fail_audit = fault == "audit"
    store.expire_after_audit = fault == "expired"
    expected = StorageUnavailableError if fault == "audit" else UnauthenticatedError
    with pytest.raises(expected):
        await reader(store)(CREDENTIAL, TARGET)
    assert not store.audit


async def unexpected_audit(session: AsyncSession, audit: OperatorAudit) -> None:
    del session, audit
    raise AssertionError("Unguarded adapter must stop before database or audit access")


@pytest.mark.parametrize("method", ["account", "conversations"])
async def test_sql_adapter_requires_actual_authority_before_query(method: str) -> None:
    async with AsyncSession() as session:
        transaction = SqlOperatorConversationIndexTransaction(session, unexpected_audit)
        operation: Awaitable[object] = (
            transaction.conversation_account(TARGET)
            if method == "account"
            else transaction.indexed_conversations(TARGET, None)
        )
        with pytest.raises(RuntimeError, match="actual current operator grant"):
            await operation
