import asyncio
from dataclasses import replace
from datetime import datetime
from http import HTTPStatus
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.application.idempotency import IntentKey
from studymate.application.profiles.goals import ReadOwnGoal, SaveGoalCommand, SaveOwnGoal
from studymate.application.requests.ports import RequestSourceChangedError
from studymate.application.requests.preview_checks import CheckedRequestPreview, PreviewBlockReason
from studymate.domain.discovery import DiscoveryMode
from studymate.domain.requests.context import RequestText
from studymate.domain.requests.limits import (
    DAILY_SEND_LIMIT,
    OUTGOING_PENDING_LIMIT,
    RequestQuotaError,
    send_day,
    send_day_bounds,
)
from studymate.domain.requests.states import UNDO_WINDOW
from studymate.infrastructure.persistence.goals import SqlGoalUnitOfWork
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.requests.models import (
    ConnectionRequestRecord,
    RequestCommandIntentRecord,
    RequestPreviewRecord,
    RequestSendDayRecord,
)
from tests.integration.requests.fixture import (
    FINGERPRINTER,
    HASHER,
    action,
    additional_peer,
    prepared,
    sent,
)
from tests.integration.requests.test_http import client

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("mode", list(DiscoveryMode))
async def test_actual_composer_http_retained_modes_and_fresh_idempotent_quota(
    identity_engine: AsyncEngine, mode: DiscoveryMode
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    async with client(api, sender) as http:
        body = {"person_id": str(recipient.id), "mode": mode.value}
        first = await http.post("/api/v1/requests/preview", json=body)
        assert first.status_code == HTTPStatus.OK, first.text
        initial = first.json()
        assert initial["can_send"]
        assert initial["block_reason"] is None
        assert initial["quota"]["daily_sends_remaining"] == DAILY_SEND_LIMIT
        assert "Synthetic course" in initial["suggested_text"]
        assert "Private source content" not in initial["suggested_text"]
        checked_at = datetime.fromisoformat(initial["checked_at"])
        assert (
            datetime.fromisoformat(initial["quota"]["reset_at"]) == send_day_bounds(checked_at)[1]
        )
        async with api.sessions.begin() as session:
            session.add(
                RequestSendDayRecord(
                    sender_id=sender.id,
                    local_day=send_day(checked_at),
                    successful_count=DAILY_SEND_LIMIT,
                )
            )
        replay = await http.post("/api/v1/requests/preview", json=body)
        assert replay.status_code == HTTPStatus.OK, replay.text
        fresh = replay.json()
        for field in ("preview_id", "created_at", "context", "suggested_text"):
            assert fresh[field] == initial[field]
        assert not fresh["can_send"]
        assert fresh["block_reason"] == "daily_send_limit"
        assert fresh["quota"]["successful_today"] == DAILY_SEND_LIMIT
        assert fresh["quota"]["daily_sends_remaining"] == 0
        assert datetime.fromisoformat(fresh["checked_at"]) >= checked_at
        assert replay.headers["cache-control"] == "no-store"
        async with api.sessions() as session:
            assert await session.scalar(select(func.count()).select_from(RequestPreviewRecord)) == 1
            assert (
                await session.scalar(select(func.count()).select_from(RequestCommandIntentRecord))
                == 1
            )
            assert (
                await session.scalar(select(func.count()).select_from(ConnectionRequestRecord)) == 0
            )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(ProductEventRecord)
                    .where(ProductEventRecord.kind == "request.changed")
                )
                == 0
            )
        http.headers["Idempotency-Key"] = str(uuid4())
        denied = await http.post(
            "/api/v1/requests",
            json={
                "person_id": str(recipient.id),
                "preview_id": fresh["preview_id"],
                "text": "Explicit reviewed draft",
            },
        )
        assert denied.status_code == HTTPStatus.TOO_MANY_REQUESTS, denied.text


async def test_current_projection_rechecks_sources_but_never_replaces_retained_draft(
    identity_engine: AsyncEngine,
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    intent = IntentKey(str(uuid4()))
    first = await api.preview.for_composer(
        sender.credential, recipient.id, DiscoveryMode.STUDY_TOGETHER, intent, api.send.limits
    )
    assert isinstance(first, CheckedRequestPreview)
    uow = SqlGoalUnitOfWork(api.sessions)
    goal = await ReadOwnGoal(uow, HASHER)(sender.credential)
    assert goal is not None
    await SaveOwnGoal(uow, HASHER, FINGERPRINTER)(
        SaveGoalCommand(
            sender.credential,
            replace(goal.goal.content, topic="Changed deliberately saved topic"),
            goal.goal.id,
            goal.goal.version,
            IntentKey(str(uuid4())),
        )
    )
    fresh = await api.preview.for_composer(
        sender.credential, recipient.id, DiscoveryMode.STUDY_TOGETHER, intent, api.send.limits
    )
    assert isinstance(fresh, CheckedRequestPreview)
    assert fresh.preview == first.preview
    assert fresh.check.block_reason == PreviewBlockReason.SOURCE_CHANGED
    with pytest.raises(RequestSourceChangedError):
        await api.send(
            sender.credential,
            recipient.id,
            first.preview.id,
            RequestText("Explicit reviewed stale draft"),
            IntentKey(str(uuid4())),
        )


async def test_five_pending_actual_sends_block_draft_without_reserving_another_slot(
    identity_engine: AsyncEngine,
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    draft = await api.preview.for_composer(
        sender.credential,
        recipient.id,
        DiscoveryMode.FIND_HELP,
        IntentKey(str(uuid4())),
        api.send.limits,
    )
    assert isinstance(draft, CheckedRequestPreview)
    for _ in range(OUTGOING_PENDING_LIMIT):
        peer = await additional_peer(identity_engine, draft.preview.context.subject_id)
        await sent(api, sender, peer)
    check = await api.preview.check_current(
        sender.credential, recipient.id, draft.preview.id, api.send.limits
    )
    assert check.quota.outgoing_pending == OUTGOING_PENDING_LIMIT
    assert check.block_reason == PreviewBlockReason.OUTGOING_PENDING_LIMIT
    with pytest.raises(RequestQuotaError):
        await api.send(
            sender.credential,
            recipient.id,
            draft.preview.id,
            RequestText("No sixth slot"),
            IntentKey(str(uuid4())),
        )
    async with api.sessions() as session:
        assert (
            await session.scalar(select(func.count()).select_from(ConnectionRequestRecord))
            == OUTGOING_PENDING_LIMIT
        )


async def test_overdue_decline_observation_is_read_only_with_actual_cooldown(
    identity_engine: AsyncEngine,
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    request = await sent(api, sender, recipient)
    declined = await api.decline(action(recipient, sender, request))
    before = len(api.recorder.transitions)
    await asyncio.sleep(UNDO_WINDOW.total_seconds())
    check = await api.preview.check_current(
        sender.credential, recipient.id, request.preview_id, api.send.limits
    )
    assert declined.decline_until is not None
    assert check.checked_at >= declined.decline_until
    assert check.block_reason == PreviewBlockReason.COOLDOWN
    assert check.cooldown_until == declined.effective(check.checked_at).sender_cooldown_until
    assert check.quota.outgoing_pending == 0
    assert len(api.recorder.transitions) == before
    async with api.sessions() as session:
        current = await session.get(ConnectionRequestRecord, request.id)
        assert current is not None
        assert current.state == "pending_decline"
        assert current.current_version == declined.version


async def test_retained_preview_replay_tracks_incoming_then_connection(
    identity_engine: AsyncEngine,
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    intent = IntentKey(str(uuid4()))
    original = await api.preview.for_composer(
        sender.credential, recipient.id, DiscoveryMode.FIND_HELP, intent, api.send.limits
    )
    assert isinstance(original, CheckedRequestPreview)
    opposite = await sent(api, recipient, sender)
    incoming = await api.preview.for_composer(
        sender.credential, recipient.id, DiscoveryMode.FIND_HELP, intent, api.send.limits
    )
    assert isinstance(incoming, CheckedRequestPreview)
    assert incoming.preview == original.preview
    assert incoming.check.block_reason == PreviewBlockReason.INCOMING
    accepted = await api.accept(action(sender, recipient, opposite))
    connected = await api.preview.for_composer(
        sender.credential, recipient.id, DiscoveryMode.FIND_HELP, intent, api.send.limits
    )
    assert isinstance(connected, CheckedRequestPreview)
    assert connected.preview == original.preview
    assert connected.check.block_reason == PreviewBlockReason.CONNECTED
    async with client(api, sender) as http:
        response = await http.post(
            "/api/v1/requests/preview", json={"person_id": str(recipient.id), "mode": "find_help"}
        )
        assert response.status_code == HTTPStatus.OK, response.text
        assert response.json()["outcome"] == "connected"
        assert response.json()["conversation_id"] == str(accepted.conversation.id)
        assert "quota" not in response.json()


async def test_current_preview_hides_peer_restriction_details_after_real_visibility_change(
    identity_engine: AsyncEngine,
) -> None:
    from tests.integration.profile_lifecycle_fixture import command, services

    sender, recipient, api = await prepared(identity_engine)
    intent = IntentKey(str(uuid4()))
    original = await api.preview.for_composer(
        sender.credential, recipient.id, DiscoveryMode.FIND_HELP, intent, api.send.limits
    )
    assert isinstance(original, CheckedRequestPreview)
    visibility, _ = services(identity_engine)
    await visibility(command(recipient))
    async with client(api, sender) as http:
        http.headers["Idempotency-Key"] = intent.value
        response = await http.post(
            "/api/v1/requests/preview", json={"person_id": str(recipient.id), "mode": "find_help"}
        )
        assert response.status_code == HTTPStatus.OK, response.text
        assert response.json()["preview_id"] == str(original.preview.id)
        assert response.json()["block_reason"] == "unavailable"
        assert not response.json()["can_send"]
        assert "hidden" not in response.json()


async def test_concurrent_current_check_and_final_send_share_actual_actor_lock_without_reservation(
    identity_engine: AsyncEngine,
) -> None:
    from studymate.application.requests.ports import SentRequest

    sender, recipient, api = await prepared(identity_engine)
    original = await api.preview.for_composer(
        sender.credential,
        recipient.id,
        DiscoveryMode.FIND_HELP,
        IntentKey(str(uuid4())),
        api.send.limits,
    )
    assert isinstance(original, CheckedRequestPreview)
    checked, result = await asyncio.gather(
        api.preview.check_current(
            sender.credential, recipient.id, original.preview.id, api.send.limits
        ),
        api.send(
            sender.credential,
            recipient.id,
            original.preview.id,
            RequestText("Explicit concurrent reviewed send"),
            IntentKey(str(uuid4())),
        ),
    )
    assert isinstance(result, SentRequest)
    assert checked.block_reason in (None, PreviewBlockReason.EXISTING_OUTGOING)
    assert checked.quota.successful_today == int(not checked.can_send)
    async with api.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(ConnectionRequestRecord)) == 1
        assert await session.scalar(select(RequestSendDayRecord.successful_count)) == 1
