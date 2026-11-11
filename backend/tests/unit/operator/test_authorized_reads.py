from dataclasses import replace
from uuid import UUID, uuid4

import pytest

from studymate.application.errors import StorageUnavailableError
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.operator.accounts import ReadOperatorAccount, SearchOperatorAccounts
from studymate.application.operator.authority import OperatorAccessDeniedError
from studymate.application.operator.filters import OperatorAccountFilters, OperatorAccountLifecycle
from studymate.application.operator.messages import ReadOperatorConversationMessages
from studymate.domain.operator.audit import (
    OPERATOR_ACCOUNT_PAGE_SIZE,
    OPERATOR_MESSAGE_PAGE_SIZE,
    OperatorAuditOutcome,
)
from studymate.infrastructure.operator.cursors import FernetOperatorCursorCodec
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.unit.identity_store import CREDENTIAL
from tests.unit.operator.store import TARGET, Store, target

HASHER = Sha256SessionHasher()
FINGERPRINTER = HmacIntentFingerprinter(b"x" * 32)
CODEC = FernetOperatorCursorCodec.from_key(b"x" * 32)


def account(store: Store) -> ReadOperatorAccount:
    return ReadOperatorAccount(store, HASHER)


def search(store: Store) -> SearchOperatorAccounts:
    return SearchOperatorAccounts(store, HASHER, FINGERPRINTER, CODEC)


def messages(store: Store) -> ReadOperatorConversationMessages:
    return ReadOperatorConversationMessages(store, HASHER, CODEC)


@pytest.mark.parametrize("denial", ["missing", "revoked", "banned", "deleted", "expired"])
async def test_no_private_query_or_audit_without_actual_live_explicit_role(denial: str) -> None:
    store = Store()
    if denial != "missing":
        store.assign_explicit_operator()
    if denial == "revoked":
        assert store.access is not None
        store.access = replace(store.access, version=2, active=False)
    elif denial == "banned":
        store.actor = replace(store.actor, banned=True)
    elif denial == "deleted":
        store.actor = replace(store.actor, deleted_at=store.clock)
    elif denial == "expired":
        store.clock = store.actor.session.expires_at
    error = UnauthenticatedError if denial in {"deleted", "expired"} else OperatorAccessDeniedError
    with pytest.raises(error):
        await account(store)(CREDENTIAL, TARGET)
    with pytest.raises(error):
        await search(store)(CREDENTIAL, OperatorAccountFilters())
    with pytest.raises(error):
        await messages(store)(CREDENTIAL, store.conversation.id)
    assert store.private_queries == 0
    assert not store.audit


async def test_explicit_operator_needs_no_student_membership_registration_or_activation() -> None:
    store = Store()
    store.assign_explicit_operator()
    store.actor = replace(
        store.actor, membership=None, registration=None, activation_complete=False
    )
    observed = await account(store)(CREDENTIAL, TARGET)
    assert observed == store.details[TARGET]
    assert observed is not None
    assert observed.account.banned_at is not None
    assert observed.account.deleted_at is not None
    assert observed.account.hidden_at is not None
    assert observed.profile is not None
    assert observed.profile.basics.display_name is not None
    assert observed.profile.basics.display_name.value == "Private original name"
    assert store.audit[-1].access == store.access
    assert store.audit[-1].outcome == OperatorAuditOutcome.READ
    assert "Private original name" not in repr(store.audit[-1])
    assert "private-stored-subject" not in repr(store.audit[-1])


async def test_missing_account_and_conversation_return_none_with_committed_notfound_audit() -> None:
    store = Store()
    store.assign_explicit_operator()
    missing = uuid4()
    assert await account(store)(CREDENTIAL, missing) is None
    assert store.audit[-1].requested is not None
    assert store.audit[-1].requested.id == missing
    assert store.audit[-1].outcome == OperatorAuditOutcome.NOT_FOUND
    assert await messages(store)(CREDENTIAL, missing) is None
    assert store.audit[-1].outcome == OperatorAuditOutcome.NOT_FOUND
    assert not store.audit[-1].results


@pytest.mark.parametrize("failure", ["audit", "query_expiry", "audit_expiry"])
async def test_failed_audit_or_final_session_check_never_returns_data(failure: str) -> None:
    store = Store()
    store.assign_explicit_operator()
    store.fail_audit = failure == "audit"
    store.expire_after_query = failure == "query_expiry"
    store.expire_after_audit = failure == "audit_expiry"
    error = StorageUnavailableError if failure == "audit" else UnauthenticatedError
    with pytest.raises(error):
        await account(store)(CREDENTIAL, TARGET)
    assert store.private_queries == 1
    assert not store.audit


async def test_search_is_bounded_anchored_and_audits_hmac_not_raw_terms_or_lookahead() -> None:
    store = Store()
    store.assign_explicit_operator()
    store.details = {
        UUID(int=index): target(UUID(int=index))
        for index in range(100, 100 + OPERATOR_ACCOUNT_PAGE_SIZE + 1)
    }
    filters = OperatorAccountFilters(
        name="Private original", lifecycle=OperatorAccountLifecycle.DELETED
    )
    first = await search(store)(CREDENTIAL, filters)
    assert len(first.accounts) == OPERATOR_ACCOUNT_PAGE_SIZE
    assert first.next_cursor is not None
    audit = store.audit[-1]
    assert len(audit.results) == len(first.accounts)
    assert audit.query_fingerprint == await FINGERPRINTER.fingerprint(filters.fingerprint_parts())
    assert "Private original" not in repr(audit)
    assert "Private original name" not in repr(audit)
    assert audit.outcome == OperatorAuditOutcome.SEARCH
    second = await search(store)(CREDENTIAL, filters, first.next_cursor)
    assert len(second.accounts) == 1
    assert second.next_cursor is None
    assert store.last_window is not None
    assert store.last_window.before is not None
    assert store.last_window.as_of == store.last_window.before.as_of


async def test_message_inspection_needs_no_participant_membership_and_audits_only_visible_ids() -> (
    None
):
    store = Store()
    store.assign_explicit_operator()
    assert store.actor.session.account_id not in (
        store.conversation.pair.low,
        store.conversation.pair.high,
    )
    for _ in range(OPERATOR_MESSAGE_PAGE_SIZE + 1):
        store.append_message()
    first = await messages(store)(CREDENTIAL, store.conversation.id)
    assert first is not None
    assert len(first.messages) == OPERATOR_MESSAGE_PAGE_SIZE
    assert first.messages[0].sequence < first.messages[-1].sequence
    assert first.messages[-1].content.text == "Private stored conversation text"
    assert first.next_cursor is not None
    assert [ref.id for ref in store.audit[-1].results] == [message.id for message in first.messages]
    assert "Private stored conversation text" not in repr(store.audit[-1])
    store.append_message()
    older = await messages(store)(CREDENTIAL, store.conversation.id, first.next_cursor)
    assert older is not None
    assert [message.sequence for message in older.messages] == [1]
    assert older.anchor_sequence == first.anchor_sequence
    assert older.next_cursor is None


async def test_empty_results_keep_search_and_read_audit_meanings() -> None:
    store = Store()
    store.assign_explicit_operator()
    page = await search(store)(
        CREDENTIAL, OperatorAccountFilters(lifecycle=OperatorAccountLifecycle.ACTIVE)
    )
    assert page.accounts == ()
    assert [entry.outcome for entry in store.audit] == [OperatorAuditOutcome.SEARCH]
    page_messages = await messages(store)(CREDENTIAL, store.conversation.id)
    assert page_messages is not None
    assert page_messages.messages == ()
    assert page_messages.anchor_sequence == 0
    assert store.audit[-1].outcome == OperatorAuditOutcome.READ
