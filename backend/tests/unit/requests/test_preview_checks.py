from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.requests.ports import (
    AlreadyConnected,
    ConversationReference,
    ExistingOutgoing,
    IncomingRequestExists,
    PairState,
)
from studymate.application.requests.preview_checks import (
    CheckedRequestPreview,
    PreviewBlockReason,
    RequestPreviewCheck,
    pair_block_reason,
)
from studymate.application.requests.send import PreviewRequest
from studymate.domain.discovery import DiscoveryMode
from studymate.domain.relationships import AccountPair
from studymate.domain.requests.context import MAX_REQUEST_TEXT, RequestText
from studymate.domain.requests.limits import RequestLimits, SendQuota, send_day_bounds
from studymate.domain.requests.states import UNDO_WINDOW, RequestUnavailableError
from studymate.domain.requests.suggestions import suggested_request_text
from studymate.domain.study_context import MAX_TOPIC_LENGTH
from studymate.presentation.requests.outputs import PreviewResponse, preview_response
from tests.unit.identity_store import CREDENTIAL, NOW
from tests.unit.requests.store import PEER, RELATIONSHIP, SENDER, Store
from tests.unit.requests.test_usecases import FINGERPRINTER, HASHER, key, preview, sent


@pytest.mark.parametrize("mode", tuple(DiscoveryMode))
async def test_each_mode_has_bounded_server_text_from_retained_context(mode: DiscoveryMode) -> None:
    store = Store()
    value = await PreviewRequest(store, HASHER, FINGERPRINTER).for_composer(
        CREDENTIAL, PEER, mode, key(), RequestLimits()
    )
    assert isinstance(value, CheckedRequestPreview)
    response = preview_response(value)
    assert isinstance(response, PreviewResponse)
    assert "Synthetic subject: Synthetic topic" in response.suggested_text
    assert "Private synthetic source" not in response.suggested_text
    RequestText(response.suggested_text)
    assert response.can_send
    assert response.block_reason is None
    assert response.quota.outgoing_pending_remaining == RequestLimits().outgoing_pending
    assert response.quota.daily_sends_remaining == RequestLimits().successful_per_day
    assert not store.requests
    assert not store.sends


async def test_long_unicode_topic_is_bounded_without_changing_retained_context() -> None:
    store = Store()
    value = await preview(store)
    goal = value.context.sender_goal
    assert goal is not None
    retained = replace(
        value.context,
        sender_goal=replace(
            goal,
            subject_label="科" * MAX_TOPIC_LENGTH,
            goal=replace(
                goal.goal, content=replace(goal.goal.content, topic="学" * MAX_TOPIC_LENGTH)
            ),
        ),
    )
    text = suggested_request_text(retained)
    assert len(text) <= MAX_REQUEST_TEXT
    assert text.endswith("学?")
    RequestText(text)
    assert retained.sender_goal is not None
    assert retained.sender_goal.goal.content.topic == "学" * MAX_TOPIC_LENGTH


async def test_preview_replay_keeps_original_but_observes_new_quota_and_kl_day() -> None:
    store = Store()
    store.clock = datetime(2026, 11, 8, 15, 59, tzinfo=UTC)
    store.actor = replace(
        store.actor,
        session=replace(store.actor.session, expires_at=store.clock + timedelta(days=2)),
    )
    usecase = PreviewRequest(store, HASHER, FINGERPRINTER)
    intent = key()
    first = await usecase.for_composer(
        CREDENTIAL, PEER, DiscoveryMode.FIND_HELP, intent, RequestLimits()
    )
    assert isinstance(first, CheckedRequestPreview)
    intents = store.intents.copy()
    store.sends.extend((SENDER, store.clock) for _ in range(10))
    full = await usecase.for_composer(
        CREDENTIAL, PEER, DiscoveryMode.FIND_HELP, intent, RequestLimits()
    )
    assert isinstance(full, CheckedRequestPreview)
    assert full.preview == first.preview
    assert full.check.block_reason == PreviewBlockReason.DAILY_SEND_LIMIT
    assert full.check.reset_at == datetime(2026, 11, 8, 16, tzinfo=UTC)
    store.clock = full.check.reset_at
    reset = await usecase.for_composer(
        CREDENTIAL, PEER, DiscoveryMode.FIND_HELP, intent, RequestLimits()
    )
    assert isinstance(reset, CheckedRequestPreview)
    assert reset.preview == first.preview
    assert reset.check.can_send
    assert reset.check.quota.successful_today == 0
    assert reset.check.checked_at > full.check.checked_at
    assert store.intents == intents
    assert len(store.previews) == 1


@pytest.mark.parametrize(
    "change", ["source", "missing_goal", "blocked", "missing_peer", "own_unavailable"]
)
async def test_current_source_or_eligibility_change_blocks_old_preview(change: str) -> None:
    store = Store()
    value = await preview(store)
    own = store.sources[SENDER]
    assert own.setup.goal is not None
    if change == "source":
        saved = own.setup.goal
        store.sources[SENDER] = replace(
            own, setup=replace(own.setup, goal=replace(saved, goal=replace(saved.goal, version=2)))
        )
    elif change == "missing_goal":
        store.sources[SENDER] = replace(own, setup=replace(own.setup, goal=None))
    elif change == "blocked":
        store.blocked = True
    elif change == "missing_peer":
        del store.sources[PEER]
    else:
        del store.sources[SENDER]
    result = await PreviewRequest(store, HASHER, FINGERPRINTER).check_current(
        CREDENTIAL, PEER, value.id, RequestLimits()
    )
    expected = (
        PreviewBlockReason.SOURCE_CHANGED
        if change in ("source", "missing_goal")
        else PreviewBlockReason.UNAVAILABLE
    )
    assert result.block_reason == expected
    assert not result.can_send
    assert store.previews[value.id] == value


async def test_current_check_never_settles_overdue_decline_or_spends_quota() -> None:
    store = Store()
    value = await sent(store)
    pending = value.decline(PEER, store.clock)
    store.requests[value.id] = pending
    store.clock += UNDO_WINDOW
    before = store.requests.copy(), store.intents.copy(), store.sends.copy()
    result = await PreviewRequest(store, HASHER, FINGERPRINTER).check_current(
        CREDENTIAL, PEER, value.preview_id, RequestLimits()
    )
    assert result.block_reason == PreviewBlockReason.COOLDOWN
    assert result.cooldown_until == pending.effective(store.clock).sender_cooldown_until
    assert result.quota.outgoing_pending == 0
    assert before == (store.requests, store.intents, store.sends)


@pytest.mark.parametrize("direction", ["outgoing", "incoming", "connected"])
async def test_current_pair_and_original_recovery_unions_are_preserved(direction: str) -> None:
    store = Store()
    value = await sent(store)
    usecase = PreviewRequest(store, HASHER, FINGERPRINTER)
    expected = PreviewBlockReason.EXISTING_OUTGOING
    recovery_type: type[ExistingOutgoing | IncomingRequestExists | AlreadyConnected] = (
        ExistingOutgoing
    )
    if direction == "incoming":
        store.as_recipient()
        # Recipient cannot read another actor's preview; exercise the exact current pair helper.
        pair = await store.observe_pair(PEER, SENDER, store.clock)
        assert pair_block_reason(pair, PEER, store.clock, SENDER)[0] == PreviewBlockReason.INCOMING
        result = await usecase.for_composer(
            CREDENTIAL, SENDER, DiscoveryMode.FIND_HELP, key(), RequestLimits()
        )
        assert isinstance(result, IncomingRequestExists)
        return
    if direction == "connected":
        ref = ConversationReference(uuid4(), RELATIONSHIP, value.pair, value.id)
        store.conversations[RELATIONSHIP] = ref
        store.requests[value.id] = value.accept(PEER, ref.id, store.clock)
        expected, recovery_type = PreviewBlockReason.CONNECTED, AlreadyConnected
    check = await usecase.check_current(CREDENTIAL, PEER, value.preview_id, RequestLimits())
    assert check.block_reason == expected
    result = await usecase.for_composer(
        CREDENTIAL, PEER, DiscoveryMode.FIND_HELP, key(), RequestLimits()
    )
    assert isinstance(result, recovery_type)


class QuotaStore(Store):
    observed = SendQuota(6, 12)

    async def quota(self, actor_id: UUID, at: datetime) -> SendQuota:
        assert actor_id == SENDER
        assert at == self.clock
        return self.observed


@pytest.mark.parametrize(
    ("counts", "reason"),
    [
        (SendQuota(6, 12), PreviewBlockReason.OUTGOING_PENDING_LIMIT),
        (SendQuota(0, 12), PreviewBlockReason.DAILY_SEND_LIMIT),
    ],
)
async def test_actual_limits_and_clamped_remaining_are_used(
    counts: SendQuota, reason: PreviewBlockReason
) -> None:
    store = QuotaStore()
    store.observed = counts
    value = await PreviewRequest(store, HASHER, FINGERPRINTER).for_composer(
        CREDENTIAL, PEER, DiscoveryMode.FIND_HELP, key(), RequestLimits(3, 4)
    )
    assert isinstance(value, CheckedRequestPreview)
    assert value.check.block_reason == reason
    output = preview_response(value)
    assert isinstance(output, PreviewResponse)
    assert output.quota.daily_sends_remaining == 0
    assert output.quota.outgoing_pending_remaining == max(0, 3 - counts.outgoing_pending)
    assert output.quota.outgoing_pending_limit == value.check.limits.outgoing_pending
    assert output.quota.daily_send_limit == value.check.limits.successful_per_day
    with pytest.raises(ValidationError):
        PreviewResponse.model_validate({**output.model_dump(), "can_send": True})
    with pytest.raises(ValidationError):
        PreviewResponse.model_validate({**output.model_dump(), "cooldown_until": NOW})


async def test_current_check_rejects_missing_foreign_and_expired_actor() -> None:
    store = Store()
    value = await preview(store)
    usecase = PreviewRequest(store, HASHER, FINGERPRINTER)
    with pytest.raises(RequestUnavailableError):
        await usecase.check_current(CREDENTIAL, PEER, uuid4(), RequestLimits())
    store.as_recipient()
    with pytest.raises(RequestUnavailableError):
        await usecase.check_current(CREDENTIAL, SENDER, value.id, RequestLimits())
    store.clock = store.actor.session.expires_at
    with pytest.raises(UnauthenticatedError):
        await usecase.check_current(CREDENTIAL, SENDER, value.id, RequestLimits())


async def test_missing_topic_uses_only_subject_and_invalid_sources_are_rejected() -> None:
    store = Store()
    value = await preview(store)
    goal = value.context.sender_goal
    assert goal is not None
    retained = replace(
        value.context,
        sender_goal=replace(
            goal, goal=replace(goal.goal, content=replace(goal.goal.content, topic=None))
        ),
    )
    assert suggested_request_text(retained) == "Could you help me with Synthetic subject?"
    with pytest.raises(ValueError, match="snapshot needs"):
        replace(value.context, sender_goal=None)
    check = RequestPreviewCheck(
        value.id, NOW, SendQuota(0, 0), RequestLimits(), send_day_bounds(NOW)[1], None, None
    )
    with pytest.raises(ValueError, match="another retained"):
        CheckedRequestPreview(replace(value, id=uuid4()), check)
    with pytest.raises(ValueError, match="day boundary"):
        replace(check, reset_at=NOW)
    with pytest.raises(ValueError, match="Only an actual"):
        replace(check, cooldown_until=NOW)
    with pytest.raises(ValueError, match="still be effective"):
        replace(check, block_reason=PreviewBlockReason.COOLDOWN, cooldown_until=NOW)
    bad = PairState(uuid4(), AccountPair.between(uuid4(), uuid4()))
    with pytest.raises(RuntimeError):
        pair_block_reason(bad, SENDER, NOW, PEER)
