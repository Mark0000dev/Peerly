from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from studymate.application.requests.sources import context
from studymate.domain.discovery import DiscoveryMode
from studymate.domain.requests.context import (
    MAX_REQUEST_TEXT,
    GoalSnapshot,
    HelpSnapshot,
    RequestText,
)
from studymate.domain.requests.limits import RequestQuotaError, SendQuota, send_day, send_day_bounds
from studymate.domain.requests.states import (
    DECLINE_COOLDOWN,
    REQUEST_LIFETIME,
    UNDO_WINDOW,
    WITHDRAW_COOLDOWN,
    ConnectionRequest,
    RequestState,
    RequestUnavailableError,
)
from tests.unit.identity_store import NOW
from tests.unit.requests.store import PEER, RELATIONSHIP, SENDER, SUBJECT, Store


def request() -> ConnectionRequest:
    store = Store()
    snapshot = context(DiscoveryMode.FIND_HELP, store.sources[SENDER], store.sources[PEER])
    return ConnectionRequest(
        uuid4(),
        RELATIONSHIP,
        uuid4(),
        snapshot,
        RequestText("Explicit reviewed text", "Separate note"),
        NOW,
        NOW,
    )


def test_decline_deadline_is_fixed_and_worker_lag_does_not_extend_cooldown() -> None:
    value = request().decline(PEER, NOW)
    assert value.decline_until == NOW + UNDO_WINDOW
    assert value.decline(PEER, NOW + timedelta(seconds=3)) == value
    assert (
        value.undo(PEER, NOW + UNDO_WINDOW - timedelta(microseconds=1)).state
        == RequestState.PENDING
    )
    with pytest.raises(RequestUnavailableError):
        value.undo(PEER, NOW + UNDO_WINDOW)
    final = value.effective(NOW + timedelta(days=2))
    assert final.state == RequestState.DECLINED
    assert final.changed_at == NOW + UNDO_WINDOW
    assert final.sender_cooldown_until == NOW + UNDO_WINDOW + DECLINE_COOLDOWN
    assert not final.pending


def test_pending_decline_blocks_accept_but_can_be_withdrawn_before_finality() -> None:
    value = request().decline(PEER, NOW)
    with pytest.raises(RequestUnavailableError):
        value.accept(PEER, uuid4(), NOW + timedelta(seconds=1))
    withdrawn = value.withdraw(SENDER, NOW + timedelta(seconds=1))
    assert withdrawn.sender_cooldown_until == NOW + timedelta(seconds=1) + WITHDRAW_COOLDOWN
    with pytest.raises(RequestUnavailableError):
        withdrawn.undo(PEER, NOW + timedelta(seconds=2))


def test_expiry_wins_if_original_request_lifetime_ends_before_undo() -> None:
    value = request()
    expiry = NOW + REQUEST_LIFETIME
    declined = value.decline(PEER, expiry - timedelta(seconds=2))
    final = declined.effective(expiry)
    assert final.state == RequestState.EXPIRED
    assert final.changed_at == expiry
    assert final.sender_cooldown_until is None
    with pytest.raises(RequestUnavailableError):
        value.withdraw(SENDER, expiry)
    assert declined.close_unavailable(expiry) == final


def test_accepted_context_and_neutral_lifecycle_close_are_immutable() -> None:
    value = request()
    conversation = uuid4()
    accepted = value.accept(PEER, conversation, NOW)
    assert accepted.conversation_id == conversation
    assert accepted.context == value.context
    assert accepted.message == value.message
    assert accepted.close_unavailable(NOW) == accepted
    closed = value.close_unavailable(NOW)
    assert closed.state == RequestState.UNAVAILABLE
    assert closed.close_unavailable(NOW) == closed
    assert accepted.effective(NOW + REQUEST_LIFETIME) == accepted


@pytest.mark.parametrize(
    "operation",
    [
        lambda value: value.accept(SENDER, uuid4(), NOW),
        lambda value: value.decline(SENDER, NOW),
        lambda value: value.undo(PEER, NOW),
        lambda value: value.withdraw(PEER, NOW),
    ],
)
def test_wrong_participant_cannot_mutate_request(
    operation: Callable[[ConnectionRequest], ConnectionRequest],
) -> None:
    with pytest.raises(RequestUnavailableError):
        operation(request())


@pytest.mark.parametrize(
    "operation",
    [
        lambda value: replace(value, version=0),
        lambda value: replace(value, version=True),
        lambda value: replace(value, changed_at=NOW - timedelta(seconds=1)),
        lambda value: replace(value, state=RequestState.ACCEPTED),
        lambda value: replace(value, conversation_id=uuid4()),
        lambda value: replace(value, decline_until=NOW),
        lambda value: replace(value, state=RequestState.PENDING_DECLINE),
        lambda value: replace(
            value, state=RequestState.PENDING_DECLINE, decline_until=NOW + timedelta(seconds=11)
        ),
    ],
)
def test_invalid_request_storage_states_are_rejected(
    operation: Callable[[ConnectionRequest], ConnectionRequest],
) -> None:
    with pytest.raises(ValueError, match=r"revision|Acceptance|Undo|pending decline"):
        operation(request())


def test_backwards_or_naive_action_time_is_rejected() -> None:
    for at in (NOW - timedelta(seconds=1), datetime(2026, 11, 7)):
        with pytest.raises(ValueError, match=r"revision|timezone|aware"):
            request().effective(at)


@pytest.mark.parametrize("text", ["x" * 241, " " * 241 + "ok", "bad\x00text", "\ud800", "  "])
def test_explicit_text_is_bounded_before_trim_and_has_safe_errors(text: str) -> None:
    with pytest.raises(ValueError, match=r"exceeds|Text"):
        RequestText(text)
    with pytest.raises(ValueError, match=r"exceeds|Text"):
        RequestText("valid", text)


def test_two_text_fields_preserve_exact_reviewed_unicode() -> None:
    value = RequestText("  " + "😀" * 238, "😀" * 240)
    assert len(value.text) == len(value.note or "") == MAX_REQUEST_TEXT
    assert "😀" not in repr(value)


@pytest.mark.parametrize("mode", list(DiscoveryMode))
def test_context_uses_exact_declared_sources_for_each_mode(mode: DiscoveryMode) -> None:
    store = Store()
    value = context(mode, store.sources[SENDER], store.sources[PEER])
    assert value.subject_id == SUBJECT
    assert "Private" not in repr(value)
    if mode == DiscoveryMode.FIND_HELP:
        assert value.sender_goal is not None
        assert value.recipient_help is not None
        assert value.recipient_goal is None
        assert value.sender_help is None
    elif mode == DiscoveryMode.OFFER_HELP:
        assert value.recipient_goal is not None
        assert value.sender_help is not None
    else:
        assert value.sender_goal is not None
        assert value.recipient_goal is not None


def test_snapshots_reject_wrong_owners_inapplicable_modes_and_invented_labels() -> None:
    value = request().context
    assert value.sender_goal is not None
    assert value.recipient_help is not None
    with pytest.raises(ValueError, match="another"):
        replace(value, sender_id=uuid4())
    with pytest.raises(ValueError, match="another"):
        replace(value, recipient_id=uuid4())
    with pytest.raises(ValueError, match="distinct"):
        replace(value, recipient_id=SENDER)
    with pytest.raises(ValueError, match="only"):
        replace(
            value,
            recipient_goal=GoalSnapshot(
                replace(value.sender_goal.goal, account_id=PEER), "Synthetic"
            ),
        )
    with pytest.raises(ValueError, match="labels"):
        HelpSnapshot(value.recipient_help.revision, ())
    with pytest.raises(ValueError, match="active"):
        GoalSnapshot(value.sender_goal.goal.complete(NOW), "Synthetic")


def test_kuala_lumpur_calendar_counts_at_midnight_not_rolling24hours() -> None:
    before = datetime(2026, 11, 7, 15, 59, 59, tzinfo=UTC)
    midnight = before + timedelta(seconds=1)
    assert send_day(midnight).day == send_day(before).day + 1
    start, end = send_day_bounds(midnight)
    assert start == midnight
    assert end - start == timedelta(days=1)
    SendQuota(4, 9).check()
    for quota in (SendQuota(5, 0), SendQuota(0, 10)):
        with pytest.raises(RequestQuotaError):
            quota.check()
    with pytest.raises(ValueError, match="negative"):
        SendQuota(-1, 0)


def test_each_mode_rejects_missing_or_no_longer_matching_declarations() -> None:
    value = request().context
    assert value.recipient_help is not None
    from studymate.domain.study_context import HelpSubjects

    empty_help = replace(
        value.recipient_help,
        revision=replace(value.recipient_help.revision, subjects=HelpSubjects()),
        labels=(),
    )
    with pytest.raises(ValueError, match="declared"):
        replace(value, recipient_help=empty_help)
    store = Store()
    offered = context(DiscoveryMode.OFFER_HELP, store.sources[SENDER], store.sources[PEER])
    assert offered.sender_help is not None
    empty_help = replace(
        offered.sender_help,
        revision=replace(offered.sender_help.revision, subjects=HelpSubjects()),
        labels=(),
    )
    with pytest.raises(ValueError, match="declared"):
        replace(offered, sender_help=empty_help)
    with pytest.raises(ValueError, match="only"):
        replace(offered, sender_help=None)
    study = context(DiscoveryMode.STUDY_TOGETHER, store.sources[SENDER], store.sources[PEER])
    assert study.sender_goal is not None
    closed_preference = replace(
        study.sender_goal,
        goal=replace(
            study.sender_goal.goal,
            content=replace(study.sender_goal.goal.content, shared_learning=False),
        ),
    )
    with pytest.raises(ValueError, match="Study"):
        replace(study, sender_goal=closed_preference)


def test_quota_defaults_are_policy_not_schema_capacity_invariants() -> None:
    from studymate.domain.requests.limits import RequestLimits

    relaxed = RequestLimits(6, 12)
    SendQuota(5, 10).check(relaxed)
    with pytest.raises(RequestQuotaError):
        SendQuota(1, 0).check(RequestLimits(1, 1))
    with pytest.raises(ValueError, match="positive"):
        RequestLimits(True, 10)
    with pytest.raises(ValueError, match="positive"):
        RequestLimits(5, 0)
