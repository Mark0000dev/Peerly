"""Discovery exposure freshness is separate from visibility/contact/lifecycle."""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from uuid import UUID

from studymate.domain.time import require_aware


@dataclass(frozen=True, slots=True)
class DiscoveryFreshnessPolicy:
    inactivity: timedelta = timedelta(days=30)

    def __post_init__(self) -> None:
        if self.inactivity <= timedelta():
            raise ValueError("Discovery inactivity interval must be positive")


@dataclass(frozen=True, slots=True)
class ExposureConfirmation:
    account_id: UUID
    confirmed_at: datetime
    previous_paused_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.confirmed_at)
        require_aware(self.previous_paused_at)
        if self.confirmed_at < self.previous_paused_at:
            raise ValueError("Confirmation cannot precede the exposure pause")


@dataclass(frozen=True, slots=True)
class DiscoveryExposure:
    account_id: UUID
    last_activity_at: datetime
    confirmed_at: datetime
    paused_at: datetime | None = None
    inactivity: timedelta = timedelta(days=30)

    def __post_init__(self) -> None:
        if self.inactivity <= timedelta():
            raise ValueError("Applied discovery inactivity interval must be positive")
        require_aware(self.last_activity_at)
        require_aware(self.confirmed_at)
        if self.last_activity_at < self.confirmed_at:
            raise ValueError("Foreground activity cannot precede its exposure confirmation")
        if self.paused_at is not None:
            require_aware(self.paused_at)
            if self.paused_at < self.confirmed_at:
                raise ValueError("Exposure pause cannot precede its last confirmation")

    def effective_pause(self, at: datetime) -> datetime | None:
        require_aware(at)
        if at < self.last_activity_at or (self.paused_at is not None and at < self.paused_at):
            raise ValueError("Freshness observation cannot precede its source facts")
        if self.paused_at is not None:
            return self.paused_at
        deadline = self.last_activity_at + self.inactivity
        return deadline if deadline <= at else None

    def record_foreground_activity(
        self, at: datetime, policy: DiscoveryFreshnessPolicy
    ) -> "DiscoveryExposure":
        # Materialize a crossed deadline BEFORE warming the activity timestamp.
        # The first return (including login) must not silently clear the pause.
        paused_at = self.effective_pause(at)
        if (
            at == self.last_activity_at
            and paused_at == self.paused_at
            and self.inactivity == policy.inactivity
        ):
            return self
        return replace(self, last_activity_at=at, paused_at=paused_at, inactivity=policy.inactivity)

    def confirm_exposure(
        self, at: datetime, policy: DiscoveryFreshnessPolicy
    ) -> tuple["DiscoveryExposure", ExposureConfirmation | None]:
        observed = self.record_foreground_activity(at, policy)
        if observed.paused_at is None:
            return observed, None
        confirmation = ExposureConfirmation(self.account_id, at, observed.paused_at)
        return replace(observed, confirmed_at=at, paused_at=None), confirmation
