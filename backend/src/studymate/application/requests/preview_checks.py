"""Current advisory state, deliberately separate from retained preview intents."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from studymate.application.requests.ports import PairState, RequestPreview
from studymate.domain.relationships import AccountPair
from studymate.domain.requests.limits import RequestLimits, SendQuota, send_day_bounds
from studymate.domain.time import require_aware


class PreviewBlockReason(StrEnum):
    EXISTING_OUTGOING = "existing_outgoing"
    INCOMING = "incoming"
    CONNECTED = "connected"
    COOLDOWN = "cooldown"
    SOURCE_CHANGED = "source_changed"
    UNAVAILABLE = "unavailable"
    OUTGOING_PENDING_LIMIT = "outgoing_pending_limit"
    DAILY_SEND_LIMIT = "daily_send_limit"


@dataclass(frozen=True, slots=True)
class RequestPreviewCheck:
    preview_id: UUID
    checked_at: datetime
    quota: SendQuota
    limits: RequestLimits
    reset_at: datetime
    block_reason: PreviewBlockReason | None
    cooldown_until: datetime | None

    def __post_init__(self) -> None:
        require_aware(self.checked_at)
        if self.reset_at != send_day_bounds(self.checked_at)[1]:
            raise ValueError("Preview quota reset must be the actual Kuala Lumpur day boundary")
        if (self.block_reason == PreviewBlockReason.COOLDOWN) != (self.cooldown_until is not None):
            raise ValueError("Only an actual cooldown may expose a cooldown deadline")
        if self.cooldown_until is not None:
            require_aware(self.cooldown_until)
            if self.cooldown_until <= self.checked_at:
                raise ValueError("Preview cooldown must still be effective")

    @property
    def can_send(self) -> bool:
        return self.block_reason is None


@dataclass(frozen=True, slots=True)
class CheckedRequestPreview:
    preview: RequestPreview = field(repr=False)
    check: RequestPreviewCheck

    def __post_init__(self) -> None:
        if self.preview.id != self.check.preview_id:
            raise ValueError("Current check belongs to another retained preview")


def pair_block_reason(
    pair: PairState | None, actor_id: UUID, at: datetime, peer_id: UUID
) -> tuple[PreviewBlockReason | None, datetime | None]:
    if pair is None:
        return None, None
    if pair.pair != AccountPair.between(actor_id, peer_id):
        raise RuntimeError("Request preview check returned another pair")
    if pair.conversation is not None:
        return PreviewBlockReason.CONNECTED, None
    if pair.pending is not None:
        return (
            PreviewBlockReason.EXISTING_OUTGOING
            if pair.pending.context.sender_id == actor_id
            else PreviewBlockReason.INCOMING
        ), None
    if pair.sender_cooldown_until is not None and at < pair.sender_cooldown_until:
        return PreviewBlockReason.COOLDOWN, pair.sender_cooldown_until
    return None, None
