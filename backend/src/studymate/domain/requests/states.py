from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from studymate.domain.relationships import AccountPair
from studymate.domain.requests.context import RequestContext, RequestText
from studymate.domain.time import require_aware

REQUEST_LIFETIME = timedelta(days=7)
UNDO_WINDOW = timedelta(seconds=10)
DECLINE_COOLDOWN = timedelta(days=7)
WITHDRAW_COOLDOWN = timedelta(hours=24)


class RequestState(StrEnum):
    PENDING = "pending"
    PENDING_DECLINE = "pending_decline"
    DECLINED = "declined"
    WITHDRAWN = "withdrawn"
    EXPIRED = "expired"
    UNAVAILABLE = "unavailable"
    ACCEPTED = "accepted"


class RequestUnavailableError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class ConnectionRequest:
    id: UUID
    relationship_id: UUID
    preview_id: UUID
    context: RequestContext = field(repr=False)
    message: RequestText = field(repr=False)
    sent_at: datetime
    changed_at: datetime
    version: int = 1
    state: RequestState = RequestState.PENDING
    decline_until: datetime | None = None
    conversation_id: UUID | None = None

    def __post_init__(self) -> None:
        require_aware(self.sent_at)
        require_aware(self.changed_at)
        if isinstance(self.version, bool) or self.version < 1 or self.changed_at < self.sent_at:
            raise ValueError("Request revision and timestamps must be valid")
        if self.decline_until is not None:
            require_aware(self.decline_until)
        if (self.state == RequestState.PENDING_DECLINE) != (self.decline_until is not None):
            raise ValueError("Only a pending decline has an Undo deadline")
        if self.decline_until is not None and self.decline_until != self.changed_at + UNDO_WINDOW:
            raise ValueError("Undo deadline is fixed ten seconds from decline")
        if (self.state == RequestState.ACCEPTED) != (self.conversation_id is not None):
            raise ValueError("Acceptance needs an actual conversation reference")

    @property
    def pair(self) -> AccountPair:
        return AccountPair.between(self.context.sender_id, self.context.recipient_id)

    @property
    def expires_at(self) -> datetime:
        return self.sent_at + REQUEST_LIFETIME

    @property
    def pending(self) -> bool:
        return self.state in {RequestState.PENDING, RequestState.PENDING_DECLINE}

    @property
    def sender_cooldown_until(self) -> datetime | None:
        if self.state == RequestState.DECLINED:
            return self.changed_at + DECLINE_COOLDOWN
        if self.state == RequestState.WITHDRAWN:
            return self.changed_at + WITHDRAW_COOLDOWN
        return None

    def effective(self, at: datetime) -> "ConnectionRequest":
        self._time(at)
        if not self.pending:
            return self
        if (
            self.decline_until is not None
            and self.decline_until < self.expires_at
            and at >= self.decline_until
        ):
            return self._change(RequestState.DECLINED, self.decline_until)
        if at >= self.expires_at:
            return self._change(RequestState.EXPIRED, self.expires_at)
        return self

    def decline(self, actor_id: UUID, at: datetime) -> "ConnectionRequest":
        value = self.effective(at)
        if actor_id != value.context.recipient_id or not value.pending:
            raise RequestUnavailableError
        if value.state == RequestState.PENDING_DECLINE:
            return value
        return value._change(RequestState.PENDING_DECLINE, at, decline_until=at + UNDO_WINDOW)

    def undo(self, actor_id: UUID, at: datetime) -> "ConnectionRequest":
        value = self.effective(at)
        if actor_id != value.context.recipient_id or value.state != RequestState.PENDING_DECLINE:
            raise RequestUnavailableError
        return value._change(RequestState.PENDING, at)

    def withdraw(self, actor_id: UUID, at: datetime) -> "ConnectionRequest":
        value = self.effective(at)
        if actor_id != value.context.sender_id or not value.pending:
            raise RequestUnavailableError
        return value._change(RequestState.WITHDRAWN, at)

    def accept(self, actor_id: UUID, conversation_id: UUID, at: datetime) -> "ConnectionRequest":
        value = self.effective(at)
        if actor_id != value.context.recipient_id or value.state != RequestState.PENDING:
            raise RequestUnavailableError
        return value._change(RequestState.ACCEPTED, at, conversation_id=conversation_id)

    def close_unavailable(self, at: datetime) -> "ConnectionRequest":
        value = self.effective(at)
        return value._change(RequestState.UNAVAILABLE, at) if value.pending else value

    def _time(self, at: datetime) -> None:
        require_aware(at)
        if at < self.changed_at:
            raise ValueError("Request action cannot precede latest revision")

    def _change(
        self,
        state: RequestState,
        at: datetime,
        *,
        decline_until: datetime | None = None,
        conversation_id: UUID | None = None,
    ) -> "ConnectionRequest":
        return replace(
            self,
            version=self.version + 1,
            state=state,
            changed_at=at,
            decline_until=decline_until,
            conversation_id=conversation_id,
        )
