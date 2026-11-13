from dataclasses import replace
from uuid import uuid4

import pytest

from studymate.application.identity.sessions import StudentActionDeniedError, UnauthenticatedError
from studymate.application.requests.response_options import ReadRequestResponseOptions
from studymate.application.requests.response_options_data import (
    MAX_RESPONSE_OPTIONS,
    LearningTooResponseOption,
    SwapResponseOption,
)
from studymate.domain.messaging import MAX_MESSAGE_LENGTH, MessageContent
from studymate.domain.requests.states import REQUEST_LIFETIME, RequestUnavailableError
from studymate.domain.study_context import (
    CanonicalSubjectRef,
    CustomSubjectRef,
    GoalContent,
    HelpSubjects,
)
from studymate.presentation.requests.response_options_models import response_options_response
from tests.unit.identity_store import CREDENTIAL, NOW
from tests.unit.requests.response_options_store import ResponseStore
from tests.unit.requests.test_usecases import HASHER


def read(store: ResponseStore) -> ReadRequestResponseOptions:
    return ReadRequestResponseOptions(store, HASHER)


async def test_both_choices_exact_sources_editable_text_and_no_private_source_in_repr() -> None:
    store = ResponseStore()
    result = await read(store)(CREDENTIAL, store.context.request.id)
    assert tuple(option.kind for option in result.options) == (
        "learning_too",
        "swap",
        "write_my_own",
    )
    assert result.default_choice == "learning_too"
    learning, swap = result.options[:2]
    assert isinstance(learning, LearningTooResponseOption)
    assert isinstance(swap, SwapResponseOption)
    saved = store.context.own.setup.goal
    help_source = store.context.peer.setup.help_subjects
    assert saved is not None
    assert help_source is not None
    assert learning.own_goal.id == saved.goal.id
    assert learning.own_goal.version == saved.goal.version
    assert swap.peer_help.version == help_source.revision.version
    assert swap.peer_help.account_id == store.context.request.context.sender_id
    assert "helping back is optional" in swap.suggested_text
    for option in result.options:
        MessageContent(option.suggested_text)
        assert len(option.suggested_text) <= MAX_MESSAGE_LENGTH
        assert "Private synthetic source" not in option.suggested_text
    assert "Synthetic topic" not in repr(result)
    assert result.request_version == store.context.request.version
    assert result.person_id == store.context.request.context.sender_id
    assert result.request_expires_at == store.context.request.expires_at


@pytest.mark.parametrize("goal_state", ["missing", "custom", "completed", "different_area"])
async def test_neutral_when_current_source_does_not_support_either_claim(goal_state: str) -> None:
    store = ResponseStore()
    own = store.context.own
    saved = own.setup.goal
    assert saved is not None
    if goal_state == "missing":
        saved = None
    elif goal_state == "completed":
        saved = replace(saved, goal=saved.goal.complete(NOW))
    else:
        subject = (
            CustomSubjectRef("Personal custom topic")
            if goal_state == "custom"
            else CanonicalSubjectRef(uuid4())
        )
        saved = replace(saved, goal=replace(saved.goal, content=GoalContent(subject)))
    store.context = replace(store.context, own=replace(own, setup=replace(own.setup, goal=saved)))
    result = await read(store)(CREDENTIAL, store.context.request.id)
    assert tuple(option.kind for option in result.options) == ("write_my_own",)
    assert result.default_choice == "write_my_own"


async def test_same_area_different_topic_not_shared_still_learning_without_false_topic_claim() -> (
    None
):
    store = ResponseStore()
    own = store.context.own
    saved = own.setup.goal
    assert saved is not None
    saved = replace(
        saved,
        goal=replace(
            saved.goal,
            version=4,
            content=replace(saved.goal.content, topic="Different own topic", shared_learning=False),
        ),
    )
    store.context = replace(store.context, own=replace(own, setup=replace(own.setup, goal=saved)))
    result = await read(store)(CREDENTIAL, store.context.request.id)
    first = result.options[0]
    assert isinstance(first, LearningTooResponseOption)
    assert first.own_goal.version == saved.goal.version
    assert "Synthetic topic" not in first.suggested_text
    assert "Different own topic" not in first.suggested_text
    assert first.own_goal.topic == "Different own topic"


async def test_removed_peer_help_keeps_learning_and_never_uses_retained_help_snapshot() -> None:
    store = ResponseStore()
    peer = store.context.peer
    help_source = peer.setup.help_subjects
    assert help_source is not None
    empty = replace(
        help_source,
        revision=replace(help_source.revision, version=2, subjects=HelpSubjects()),
        labels=(),
    )
    store.context = replace(
        store.context, peer=replace(peer, setup=replace(peer.setup, help_subjects=empty))
    )
    result = await read(store)(CREDENTIAL, store.context.request.id)
    assert tuple(option.kind for option in result.options) == ("learning_too", "write_my_own")
    assert result.default_choice == "learning_too"


async def test_swap_only_uses_actual_different_own_area_matched_current_peer_help() -> None:
    from studymate.domain.study_context import HelpSubject

    store = ResponseStore()
    own, peer = store.context.own, store.context.peer
    saved, declared = own.setup.goal, peer.setup.help_subjects
    assert saved is not None
    assert declared is not None
    other_area = uuid4()
    saved = replace(
        saved,
        subject_label="Other area",
        goal=replace(
            saved.goal,
            version=4,
            content=replace(saved.goal.content, subject=CanonicalSubjectRef(other_area)),
        ),
    )
    declared = replace(
        declared,
        revision=replace(
            declared.revision, version=7, subjects=HelpSubjects((HelpSubject(other_area),))
        ),
        labels=("Other area",),
    )
    store.context = replace(
        store.context,
        own=replace(own, setup=replace(own.setup, goal=saved)),
        peer=replace(peer, setup=replace(peer.setup, help_subjects=declared)),
    )
    result = await read(store)(CREDENTIAL, store.context.request.id)
    assert tuple(option.kind for option in result.options) == ("swap", "write_my_own")
    assert result.default_choice == "swap"
    swap = result.options[0]
    assert isinstance(swap, SwapResponseOption)
    assert swap.peer_help.version == declared.revision.version
    assert swap.peer_help.subject_id == other_area


@pytest.mark.parametrize(
    "fault",
    [
        "unavailable",
        "wrong_request",
        "expired",
        "declined",
        "accepted",
        "blocked",
        "own_hidden",
        "peer_deleted",
        "peer_banned",
    ],
)
async def test_unavailable_or_no_longer_accept_capable_never_yields_source_claims(
    fault: str,
) -> None:
    store = ResponseStore()
    if fault == "unavailable":
        store.unavailable = True
    elif fault == "wrong_request":
        store.context = replace(store.context, request=replace(store.context.request, id=uuid4()))
    elif fault == "expired":
        store.clock = NOW + REQUEST_LIFETIME
    elif fault == "declined":
        store.context = replace(
            store.context,
            request=store.context.request.decline(store.actor.session.account_id, NOW),
        )
    elif fault == "accepted":
        store.context = replace(
            store.context,
            request=store.context.request.accept(store.actor.session.account_id, uuid4(), NOW),
        )
    elif fault == "blocked":
        store.context = replace(store.context, blocked=True)
    elif fault == "own_hidden":
        own = store.context.own
        assert own.setup.lifecycle is not None
        store.context = replace(
            store.context,
            own=replace(
                own, setup=replace(own.setup, lifecycle=replace(own.setup.lifecycle, hidden_at=NOW))
            ),
        )
    elif fault == "peer_deleted":
        store.context = replace(store.context, peer=replace(store.context.peer, deleted=True))
    elif fault == "peer_banned":
        store.context = replace(store.context, peer=replace(store.context.peer, banned=True))
    error = (
        RuntimeError
        if fault == "wrong_request"
        else (UnauthenticatedError if fault == "expired" else RequestUnavailableError)
    )
    with pytest.raises(error):
        await read(store)(
            CREDENTIAL, uuid4() if fault == "wrong_request" else store.context.request.id
        )


@pytest.mark.parametrize("fault", ["membership", "activation", "banned", "deleted", "expired"])
async def test_actor_guard_precedes_any_source_read(fault: str) -> None:
    store = ResponseStore()
    if fault == "membership":
        store.actor = replace(store.actor, membership=None)
    elif fault == "activation":
        store.actor = replace(store.actor, activation_complete=False)
    elif fault == "banned":
        store.actor = replace(store.actor, banned=True)
    elif fault == "deleted":
        store.actor = replace(store.actor, deleted_at=NOW)
    else:
        store.clock = store.actor.session.expires_at
    with pytest.raises((UnauthenticatedError, StudentActionDeniedError)):
        await read(store)(CREDENTIAL, store.context.request.id)
    assert store.source_reads == 0


async def test_final_session_expiry_cannot_return_prefilled_private_goal() -> None:
    store = ResponseStore()
    store.expire_after_read = True
    with pytest.raises(UnauthenticatedError):
        await read(store)(CREDENTIAL, store.context.request.id)


async def test_strict_tagged_output_has_only_matched_refs_and_no_capability_or_request_writes() -> (
    None
):
    store = ResponseStore()
    result = await read(store)(CREDENTIAL, store.context.request.id)
    output = response_options_response(result)
    assert output.default_choice == output.options[0].kind
    assert len(output.options) <= MAX_RESPONSE_OPTIONS
    assert "source_digest" not in output.model_dump_json()
    assert "Private synthetic source" not in output.model_dump_json()
    assert not hasattr(output, "conversation_id")
    assert not hasattr(output, "disclosure_id")
    assert "Synthetic topic" not in repr(output)
