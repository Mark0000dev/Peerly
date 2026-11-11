from dataclasses import replace
from uuid import uuid4

import pytest

from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.operator.cursors import InvalidOperatorCursorError, OperatorCursorScope
from studymate.application.operator.filters import OperatorAccountFilters
from studymate.application.operator.ports import OperatorMessagePosition
from studymate.domain.operator.audit import OPERATOR_ACCOUNT_PAGE_SIZE, OPERATOR_MESSAGE_PAGE_SIZE
from tests.unit.identity_store import CREDENTIAL
from tests.unit.operator.store import TARGET, Store, target
from tests.unit.operator.test_authorized_reads import CODEC, account, messages, search


async def test_foreign_role_source_and_expiry_during_role_lookup_never_reach_private_query() -> (
    None
):
    store = Store()
    store.assign_explicit_operator()
    assert store.access is not None
    store.access = replace(store.access, account_id=uuid4())
    with pytest.raises(RuntimeError, match="another authenticated account"):
        await account(store)(CREDENTIAL, TARGET)
    store.assign_explicit_operator()
    store.expire_after_role = True
    with pytest.raises(UnauthenticatedError):
        await account(store)(CREDENTIAL, TARGET)
    assert not store.private_queries
    assert not store.audit


@pytest.mark.parametrize("violation", ["oversized", "unordered", "future"])
async def test_account_source_order_and_bounds_cannot_be_hidden_by_successful_audit(
    violation: str,
) -> None:
    store = Store()
    store.assign_explicit_operator()
    summary = store.details[TARGET].account
    if violation == "oversized":
        store.account_rows = (summary,) * (OPERATOR_ACCOUNT_PAGE_SIZE + 2)
    elif violation == "unordered":
        store.account_rows = (summary, summary)
    else:
        store.account_rows = (replace(summary, created_at=store.actor.session.expires_at),)
    with pytest.raises(RuntimeError, match=r"bounded|ordering"):
        await search(store)(CREDENTIAL, OperatorAccountFilters())
    assert not store.audit


async def test_account_and_conversation_projection_must_match_actual_requested_ids() -> None:
    store = Store()
    store.assign_explicit_operator()
    store.details[TARGET] = target(uuid4())
    with pytest.raises(RuntimeError, match="another target"):
        await account(store)(CREDENTIAL, TARGET)
    assert not store.audit


@pytest.mark.parametrize("violation", ["oversized", "unordered", "foreign"])
async def test_inspection_never_returns_unbounded_unordered_or_other_resource_payload(
    violation: str,
) -> None:
    store = Store()
    store.assign_explicit_operator()
    message = store.append_message()
    if violation == "oversized":
        store.message_rows = (message,) * (OPERATOR_MESSAGE_PAGE_SIZE + 2)
    elif violation == "unordered":
        store.message_rows = (message, message)
    else:
        store.message_rows = (replace(message, conversation_id=uuid4()),)
    with pytest.raises(RuntimeError, match=r"bounded|ordering"):
        await messages(store)(CREDENTIAL, store.conversation.id)
    assert not store.audit


async def test_valid_operator_still_cannot_supply_a_future_conversation_anchor() -> None:
    store = Store()
    store.assign_explicit_operator()
    assert store.access is not None
    token = CODEC.encode_messages(
        OperatorCursorScope(store.access.account_id, store.access.version),
        store.conversation.id,
        OperatorMessagePosition(1, 1),
    )
    with pytest.raises(InvalidOperatorCursorError):
        await messages(store)(CREDENTIAL, store.conversation.id, token)
    assert not store.audit
