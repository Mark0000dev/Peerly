import asyncio
from dataclasses import replace
from datetime import timedelta
from functools import partial
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest

from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.sessions import StudentActionDeniedError, UnauthenticatedError
from studymate.application.requests.actions import (
    AcceptRequest,
    DeclineRequest,
    RequestAction,
    UndoDecline,
    WithdrawRequest,
)
from studymate.application.requests.ports import (
    AcceptedRequest,
    AlreadyConnected,
    ConversationReference,
    ExistingOutgoing,
    IncomingRequestExists,
    RequestCooldownError,
    RequestPreview,
    RequestSourceChangedError,
    RequestVersionConflictError,
    SentRequest,
)
from studymate.application.requests.send import PreviewRequest, SendRequest
from studymate.domain.discovery import DiscoveryMode
from studymate.domain.relationships import AccountPair
from studymate.domain.requests.context import RequestText
from studymate.domain.requests.limits import (
    DAILY_SEND_LIMIT,
    OUTGOING_PENDING_LIMIT,
    RequestQuotaError,
)
from studymate.domain.requests.states import (
    UNDO_WINDOW,
    ConnectionRequest,
    RequestState,
    RequestUnavailableError,
)
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.unit.identity_store import CREDENTIAL, NOW
from tests.unit.requests.store import PEER, RELATIONSHIP, SENDER, Store
from tests.unit.requests.test_states import request

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

HASHER = Sha256SessionHasher()
FINGERPRINTER = HmacIntentFingerprinter(b"x" * 32)


def key() -> IntentKey:
    return IntentKey(str(uuid4()))


def command(value: ConnectionRequest, peer: UUID) -> RequestAction:
    return RequestAction(CREDENTIAL, peer, value.id, value.version, key())


async def preview(store: Store) -> RequestPreview:
    result = await PreviewRequest(store, HASHER, FINGERPRINTER)(
        CREDENTIAL, PEER, DiscoveryMode.FIND_HELP, key()
    )
    assert isinstance(result, RequestPreview)
    return result


async def sent(store: Store) -> ConnectionRequest:
    value = await preview(store)
    result = await SendRequest(store, HASHER, FINGERPRINTER)(
        CREDENTIAL, PEER, value.id, RequestText("Explicit reviewed text", "Separate note"), key()
    )
    assert isinstance(result, SentRequest)
    return result.request


async def test_preview_retains_sources_but_never_sends_and_replays_original() -> None:
    store = Store()
    usecase = PreviewRequest(store, HASHER, FINGERPRINTER)
    intent = key()
    result = await usecase(CREDENTIAL, PEER, DiscoveryMode.FIND_HELP, intent)
    assert isinstance(result, RequestPreview)
    assert not store.requests
    assert not store.sends
    assert not store.conversations
    assert result.context.sender_goal is not None
    own_goal = store.sources[SENDER].setup.goal
    assert own_goal is not None
    assert result.context.sender_goal.goal == own_goal.goal
    store.blocked = True
    assert await usecase(CREDENTIAL, PEER, DiscoveryMode.FIND_HELP, intent) == result
    with pytest.raises(IdempotencyConflictError):
        await usecase(CREDENTIAL, PEER, DiscoveryMode.OFFER_HELP, intent)


async def test_concurrent_retry_creates_one_send_and_intent_replay_preserves_original() -> None:
    store = Store()
    value = await preview(store)
    intent = key()
    message = RequestText("Exact reviewed text")
    send = SendRequest(store, HASHER, FINGERPRINTER)
    first, replayed = await asyncio.gather(
        send(CREDENTIAL, PEER, value.id, message, intent),
        send(CREDENTIAL, PEER, value.id, message, intent),
    )
    assert first == replayed
    assert isinstance(first, SentRequest)
    assert len(store.requests) == len(store.sends) == 1
    await WithdrawRequest(store, HASHER, FINGERPRINTER)(command(first.request, PEER))
    assert await send(CREDENTIAL, PEER, value.id, message, intent) == first
    with pytest.raises(IdempotencyConflictError):
        await send(CREDENTIAL, PEER, value.id, RequestText(message.text, "Changed note"), intent)


async def test_same_pair_new_payload_returns_original_outgoing_without_spending() -> None:
    store = Store()
    first = await sent(store)
    assert await PreviewRequest(store, HASHER, FINGERPRINTER)(
        CREDENTIAL, PEER, DiscoveryMode.FIND_HELP, key()
    ) == ExistingOutgoing(first)
    value = store.previews[first.preview_id]
    result = await SendRequest(store, HASHER, FINGERPRINTER)(
        CREDENTIAL, PEER, value.id, RequestText("Different reviewed draft"), key()
    )
    assert result == ExistingOutgoing(first)
    assert len(store.sends) == 1


async def test_opposite_send_returns_incoming_and_never_autoaccepts() -> None:
    store = Store()
    original_actor = store.actor
    store.as_recipient()
    value = await PreviewRequest(store, HASHER, FINGERPRINTER)(
        CREDENTIAL, SENDER, DiscoveryMode.FIND_HELP, key()
    )
    assert isinstance(value, RequestPreview)
    store.actor = original_actor
    first = await sent(store)
    store.as_recipient()
    recovered = await PreviewRequest(store, HASHER, FINGERPRINTER)(
        CREDENTIAL, SENDER, DiscoveryMode.FIND_HELP, key()
    )
    assert recovered == IncomingRequestExists(first)
    result = await SendRequest(store, HASHER, FINGERPRINTER)(
        CREDENTIAL, SENDER, value.id, RequestText("My preserved opposite draft"), key()
    )
    assert result == IncomingRequestExists(first)
    assert not store.conversations
    assert len(store.sends) == 1


async def test_existing_connection_returns_actual_foundation_reference() -> None:
    store = Store()
    value = await preview(store)
    actual = ConversationReference(
        uuid4(), RELATIONSHIP, AccountPair.between(SENDER, PEER), uuid4()
    )
    store.conversations[RELATIONSHIP] = actual
    result = await SendRequest(store, HASHER, FINGERPRINTER)(
        CREDENTIAL, PEER, value.id, RequestText("New draft"), key()
    )
    assert result == AlreadyConnected(actual)
    assert not store.sends


@pytest.mark.parametrize("kind", ["edit_goal", "complete_goal", "edit_help", "foreign", "missing"])
async def test_send_rechecks_exact_owned_source_snapshot(kind: str) -> None:
    store = Store()
    value = await preview(store)
    if kind in {"edit_goal", "complete_goal"}:
        own = store.sources[SENDER]
        assert own.setup.goal is not None
        goal = own.setup.goal.goal
        goal = (
            goal.complete(NOW)
            if kind == "complete_goal"
            else goal.revise(replace(goal.content, context="Changed private source"), NOW)
        )
        store.sources[SENDER] = replace(
            own, setup=replace(own.setup, goal=replace(own.setup.goal, goal=goal))
        )
    elif kind == "edit_help":
        peer = store.sources[PEER]
        assert peer.setup.help_subjects is not None
        help_snapshot = peer.setup.help_subjects
        store.sources[PEER] = replace(
            peer,
            setup=replace(
                peer.setup,
                help_subjects=replace(
                    help_snapshot, revision=replace(help_snapshot.revision, version=2)
                ),
            ),
        )
    elif kind == "foreign":
        # Another sender's preview is never a grant even if target matches.
        store.as_recipient()
    else:
        store.previews.clear()
    peer_id = SENDER if kind == "foreign" else PEER
    expected = (
        RequestUnavailableError if kind in {"foreign", "missing"} else RequestSourceChangedError
    )
    with pytest.raises(expected):
        await SendRequest(store, HASHER, FINGERPRINTER)(
            CREDENTIAL, peer_id, value.id, RequestText("Reviewed"), key()
        )
    assert not store.sends


@pytest.mark.parametrize(
    "state",
    [
        "unactivated",
        "unverified",
        "banned",
        "deleted",
        "hidden",
        "peer_hidden",
        "blocked",
        "own_missing",
        "peer_missing",
    ],
)
async def test_preview_and_send_eligibility_is_server_owned(state: str) -> None:
    store = Store()
    value = await preview(store)
    error: type[Exception] = StudentActionDeniedError
    if state == "unactivated":
        store.actor = replace(store.actor, activation_complete=False)
    elif state == "unverified":
        store.actor = replace(store.actor, membership=None)
    elif state == "banned":
        store.actor = replace(store.actor, banned=True)
    elif state == "deleted":
        store.actor = replace(store.actor, deleted_at=NOW)
        error = UnauthenticatedError
    elif state in {"hidden", "peer_hidden"}:
        owner = SENDER if state == "hidden" else PEER
        current = store.sources[owner]
        assert current.setup.lifecycle is not None
        store.sources[owner] = replace(
            current,
            setup=replace(
                current.setup,
                lifecycle=current.setup.lifecycle.with_visibility(hidden=True, at=NOW),
            ),
        )
        if state == "peer_hidden":
            error = RequestUnavailableError
    elif state == "blocked":
        store.blocked = True
        error = RequestUnavailableError
    elif state == "own_missing":
        del store.sources[SENDER]
    else:
        del store.sources[PEER]
        error = RequestUnavailableError
    with pytest.raises(error):
        await SendRequest(store, HASHER, FINGERPRINTER)(
            CREDENTIAL, PEER, value.id, RequestText("Reviewed"), key()
        )
    assert not store.requests


async def test_limits_count_other_pairs_and_successful_sends_not_withdrawals() -> None:
    store = Store()
    for number in range(OUTGOING_PENDING_LIMIT):
        base = request()
        assert base.context.recipient_help is not None
        recipient = UUID(int=100 + number)
        help_snapshot = replace(
            base.context.recipient_help,
            revision=replace(base.context.recipient_help.revision, account_id=recipient),
        )
        snapshot = replace(base.context, recipient_id=recipient, recipient_help=help_snapshot)
        outgoing = replace(base, relationship_id=uuid4(), context=snapshot)
        store.requests[outgoing.id] = outgoing
    value = await preview(store)
    with pytest.raises(RequestQuotaError):
        await SendRequest(store, HASHER, FINGERPRINTER)(
            CREDENTIAL, PEER, value.id, RequestText("Reviewed"), key()
        )
    store.requests.clear()
    store.sends = [(SENDER, NOW)] * DAILY_SEND_LIMIT
    with pytest.raises(RequestQuotaError):
        await SendRequest(store, HASHER, FINGERPRINTER)(
            CREDENTIAL, PEER, value.id, RequestText("Reviewed"), key()
        )
    store.actor = replace(
        store.actor, session=replace(store.actor.session, expires_at=NOW + timedelta(days=30))
    )
    store.clock += timedelta(days=1)
    result = await SendRequest(store, HASHER, FINGERPRINTER)(
        CREDENTIAL, PEER, value.id, RequestText("Reviewed"), key()
    )
    assert isinstance(result, SentRequest)


async def test_pending_decline_holds_pair_and_quota_and_recipient_may_initiate_after_finality() -> (
    None
):
    store = Store()
    first = await sent(store)
    store.as_recipient()
    declining = await DeclineRequest(store, HASHER, FINGERPRINTER)(command(first, SENDER))
    assert (await store.quota(SENDER, NOW)).outgoing_pending == 1
    value = await PreviewRequest(store, HASHER, FINGERPRINTER)(
        CREDENTIAL, SENDER, DiscoveryMode.FIND_HELP, key()
    )
    assert value == IncomingRequestExists(declining)
    with pytest.raises(RequestUnavailableError):
        await AcceptRequest(store, HASHER, FINGERPRINTER)(command(declining, SENDER))
    store.clock += UNDO_WINDOW
    value = await PreviewRequest(store, HASHER, FINGERPRINTER)(
        CREDENTIAL, SENDER, DiscoveryMode.FIND_HELP, key()
    )
    assert isinstance(value, RequestPreview)
    result = await SendRequest(store, HASHER, FINGERPRINTER)(
        CREDENTIAL, SENDER, value.id, RequestText("Opposite reviewed"), key()
    )
    assert isinstance(result, SentRequest)
    assert result.request.context.sender_id == PEER


async def test_decline_undo_rechecks_eligibility_and_key_does_not_extend_deadline() -> None:
    store = Store()
    first = await sent(store)
    store.as_recipient()
    decline = DeclineRequest(store, HASHER, FINGERPRINTER)
    action = command(first, SENDER)
    value = await decline(action)
    store.clock += timedelta(seconds=2)
    assert await decline(action) == value
    store.blocked = True
    with pytest.raises(RequestUnavailableError):
        await UndoDecline(store, HASHER, FINGERPRINTER)(command(value, SENDER))
    store.blocked = False
    undone = await UndoDecline(store, HASHER, FINGERPRINTER)(command(value, SENDER))
    assert undone.state == RequestState.PENDING
    assert undone.decline_until is None


async def test_withdraw_does_not_refund_daily_count_and_imposes_sender_only_cooldown() -> None:
    store = Store()
    first = await sent(store)
    action = command(first, PEER)
    usecase = WithdrawRequest(store, HASHER, FINGERPRINTER)
    withdrawn = await usecase(action)
    assert await usecase(action) == withdrawn
    assert len(store.sends) == 1
    assert (await store.quota(SENDER, NOW)).outgoing_pending == 0
    with pytest.raises(RequestCooldownError):
        await preview(store)
    value = store.previews[first.preview_id]
    with pytest.raises(RequestCooldownError):
        await SendRequest(store, HASHER, FINGERPRINTER)(
            CREDENTIAL, PEER, value.id, RequestText("Reviewed"), key()
        )


@pytest.mark.parametrize("failure", ["session", "foundation", "wrong_reference"])
async def test_acceptance_rolls_back_request_conversation_and_intent_on_failure(
    failure: str,
) -> None:
    store = Store()
    first = await sent(store)
    store.as_recipient()
    store.expire_on_save = failure == "session"
    store.fail_conversation = failure == "foundation"
    store.bad_conversation = failure == "wrong_reference"
    expected = UnauthenticatedError if failure == "session" else RuntimeError
    with pytest.raises(expected):
        await AcceptRequest(store, HASHER, FINGERPRINTER)(command(first, SENDER))
    assert not store.conversations
    assert store.requests[first.id] == first
    assert not any(operation == "accept" for _, operation, _ in store.intents)


async def test_acceptance_uses_real_port_reference_and_replays_exact_result() -> None:
    store = Store()
    first = await sent(store)
    store.as_recipient()
    action = command(first, SENDER)
    accept = AcceptRequest(store, HASHER, FINGERPRINTER)
    value = await accept(action)
    assert isinstance(value, AcceptedRequest)
    assert value.conversation == store.conversations[RELATIONSHIP]
    assert value.request.conversation_id == value.conversation.id
    assert value.request.context == first.context
    assert await accept(action) == value
    assert len(store.conversations) == 1


async def test_session_expiry_rolls_back_preview_and_send() -> None:
    store = Store()
    store.expire_on_save = True
    with pytest.raises(UnauthenticatedError):
        await preview(store)
    assert not store.previews
    store.clock = NOW
    store.expire_on_save = False
    value = await preview(store)
    store.expire_on_save = True
    with pytest.raises(UnauthenticatedError):
        await SendRequest(store, HASHER, FINGERPRINTER)(
            CREDENTIAL, PEER, value.id, RequestText("Reviewed"), key()
        )
    assert not store.requests
    assert not store.sends


async def test_stale_revision_and_unknown_request_are_not_mutated() -> None:
    store = Store()
    first = await sent(store)
    with pytest.raises(RequestVersionConflictError):
        await WithdrawRequest(store, HASHER, FINGERPRINTER)(
            replace(command(first, PEER), expected_version=2)
        )
    with pytest.raises(RequestUnavailableError):
        await WithdrawRequest(store, HASHER, FINGERPRINTER)(
            replace(command(first, PEER), request_id=uuid4())
        )
    assert store.requests[first.id] == first


async def test_undo_replay_keeps_original_revision_and_conflicts_on_changed_intent() -> None:
    store = Store()
    first = await sent(store)
    store.as_recipient()
    declined = await DeclineRequest(store, HASHER, FINGERPRINTER)(command(first, SENDER))
    action = command(declined, SENDER)
    undo = UndoDecline(store, HASHER, FINGERPRINTER)
    value = await undo(action)
    assert await undo(action) == value
    with pytest.raises(IdempotencyConflictError):
        await undo(replace(action, expected_version=value.version))


@pytest.mark.parametrize("version", [0, -1, True])
def test_action_has_strict_positive_revision(version: int) -> None:
    with pytest.raises(ValueError, match="positive"):
        RequestAction(CREDENTIAL, PEER, uuid4(), version, key())


async def test_source_adapter_cannot_substitute_another_accounts_snapshot() -> None:
    store = Store()
    store.sources[SENDER] = store.sources[PEER]
    with pytest.raises(RuntimeError, match="another account"):
        await preview(store)
    assert not store.previews


def test_pair_projection_cannot_substitute_history_or_conversation_from_another_pair() -> None:
    from studymate.application.requests.ports import PairState

    value = request()
    pair = AccountPair.between(SENDER, PEER)
    with pytest.raises(ValueError, match="another relationship"):
        PairState(uuid4(), pair, value)
    with pytest.raises(ValueError, match="effective"):
        PairState(RELATIONSHIP, pair, value.withdraw(SENDER, NOW))
    conversation = ConversationReference(uuid4(), RELATIONSHIP, pair, value.id)
    with pytest.raises(ValueError, match="active pending"):
        PairState(RELATIONSHIP, pair, value, conversation)


@pytest.mark.parametrize(
    "operation_name", ["preview", "send", "decline", "undo", "withdraw", "accept"]
)
async def test_cross_operation_stored_outcome_is_rejected_instead_of_claiming_success(
    operation_name: str,
) -> None:
    store = Store()
    intent = key()
    operation: Callable[[], Awaitable[object]]
    if operation_name == "preview":
        usecase = PreviewRequest(store, HASHER, FINGERPRINTER)
        operation = partial(usecase, CREDENTIAL, PEER, DiscoveryMode.FIND_HELP, intent)
    elif operation_name == "send":
        value = await preview(store)
        sender = SendRequest(store, HASHER, FINGERPRINTER)
        operation = partial(sender, CREDENTIAL, PEER, value.id, RequestText("Reviewed"), intent)
    else:
        first = await sent(store)
        if operation_name != "withdraw":
            store.as_recipient()
        peer = PEER if operation_name == "withdraw" else SENDER
        if operation_name == "undo":
            first = await DeclineRequest(store, HASHER, FINGERPRINTER)(command(first, peer))
        action = replace(command(first, peer), key=intent)
        if operation_name == "decline":
            decline = DeclineRequest(store, HASHER, FINGERPRINTER)
            operation = partial(decline, action)
        elif operation_name == "undo":
            undo = UndoDecline(store, HASHER, FINGERPRINTER)
            operation = partial(undo, action)
        elif operation_name == "withdraw":
            withdraw = WithdrawRequest(store, HASHER, FINGERPRINTER)
            operation = partial(withdraw, action)
        else:
            accept = AcceptRequest(store, HASHER, FINGERPRINTER)
            operation = partial(accept, action)
    await operation()
    stored_key = (store.actor.session.account_id, operation_name, intent.value)
    original = store.intents[stored_key]
    wrong = request() if operation_name == "preview" else next(iter(store.previews.values()))
    store.intents[stored_key] = replace(original, result=wrong)
    with pytest.raises(RuntimeError, match="wrong result type"):
        await operation()


async def test_acceptance_rechecks_deadline_after_conversation_sql_boundary() -> None:
    store = Store()
    first = await sent(store)
    store.as_recipient()
    store.actor = replace(
        store.actor, session=replace(store.actor.session, expires_at=NOW + timedelta(days=30))
    )
    store.expire_request_on_conversation = True
    with pytest.raises(RequestUnavailableError):
        await AcceptRequest(store, HASHER, FINGERPRINTER)(command(first, SENDER))
    assert not store.conversations
    assert store.requests[first.id] == first
    assert not any(operation == "accept" for _, operation, _ in store.intents)


async def test_existing_conversation_recovery_does_not_require_new_contact_eligibility() -> None:
    store = Store()
    value = await preview(store)
    actual = ConversationReference(
        uuid4(), RELATIONSHIP, AccountPair.between(SENDER, PEER), uuid4()
    )
    store.conversations[RELATIONSHIP] = actual
    store.sources.clear()
    store.blocked = True
    result = await SendRequest(store, HASHER, FINGERPRINTER)(
        CREDENTIAL, PEER, value.id, RequestText("Retained reviewed intent"), key()
    )
    assert result == AlreadyConnected(actual)
    assert not store.sends


async def test_preview_recovers_actual_pair_before_composer_and_replays_original() -> None:
    store = Store()
    first = await sent(store)
    usecase = PreviewRequest(store, HASHER, FINGERPRINTER)
    intent = key()
    store.blocked = True
    result = await usecase(CREDENTIAL, PEER, DiscoveryMode.FIND_HELP, intent)
    assert result == ExistingOutgoing(first)
    assert len(store.previews) == 1
    store.as_recipient()
    incoming = await usecase(CREDENTIAL, SENDER, DiscoveryMode.OFFER_HELP, key())
    assert incoming == IncomingRequestExists(first)
    # Recovering the existing request does not autoaccept or use a new draft.
    assert not store.conversations
    store.blocked = False
    accepted = await AcceptRequest(store, HASHER, FINGERPRINTER)(command(first, SENDER))
    store.blocked = True
    connected = await usecase(CREDENTIAL, SENDER, DiscoveryMode.FIND_HELP, key())
    assert connected == AlreadyConnected(accepted.conversation)
    store.actor = replace(store.actor, session=replace(store.actor.session, account_id=SENDER))
    assert await usecase(CREDENTIAL, PEER, DiscoveryMode.FIND_HELP, intent) == result
    assert len(store.sends) == 1


async def test_elapsed_undo_rejects_state_without_fabricating_a_stored_version() -> None:
    store = Store()
    first = await sent(store)
    store.as_recipient()
    declined = await DeclineRequest(store, HASHER, FINGERPRINTER)(command(first, SENDER))
    store.clock += UNDO_WINDOW
    with pytest.raises(RequestUnavailableError):
        await UndoDecline(store, HASHER, FINGERPRINTER)(command(declined, SENDER))
    assert store.requests[first.id].version == declined.version
