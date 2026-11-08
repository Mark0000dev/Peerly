"""Retained account flags and immutable actual lifecycle sources, never a purge/restore."""

from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from studymate.domain.operator.access import OperatorAccess
from studymate.domain.text import plain_text
from studymate.domain.time import require_aware

MAX_LIFECYCLE_SOURCE_VERSION = (1 << 31) - 1
# Implementation input bound, not a claim of an independently approved product-policy maximum.
MAX_LIFECYCLE_REASON_CHARACTERS = 1000


class LifecycleOperation(StrEnum):
    BAN = "ban"
    UNBAN = "unban"
    DELETE = "delete"


class DeletedLifecycleAccountError(Exception):
    """A new deletion cannot re-create/restore an already deleted identity."""


@dataclass(frozen=True, slots=True)
class LifecycleReason:
    value: str = field(repr=False)

    def __post_init__(self) -> None:
        if not 1 <= len(self.value) <= MAX_LIFECYCLE_REASON_CHARACTERS or not self.value.strip():
            raise ValueError("Lifecycle reason requires bounded nonblank private text")
        # Validate existing plain-text control/surrogate policy without taking its
        # normalized return value: stored reason/HMAC keep exact submitted whitespace.
        plain_text(self.value, minimum=1, maximum=MAX_LIFECYCLE_REASON_CHARACTERS, multiline=True)
        # Keep exact submitted whitespace and Unicode for retained business evidence/HMAC.


@dataclass(frozen=True, slots=True)
class AccountLifecycle:
    account_id: UUID
    banned_at: datetime | None = None
    deleted_at: datetime | None = None
    source_version: int = 0

    def __post_init__(self) -> None:
        for value in (self.banned_at, self.deleted_at):
            if value is not None:
                require_aware(value)
        if (
            isinstance(self.source_version, bool)
            or not 0 <= self.source_version <= MAX_LIFECYCLE_SOURCE_VERSION
        ):
            raise ValueError("Lifecycle snapshot needs its actual retained source version")
        # Zero means NO recorded new lifecycle source, including existing legacy flags.
        # No original operator/reason/consent/history is inferred from legacy timestamps.

    @property
    def account_allows_student_actions(self) -> bool:
        # Lifecycle gate only; membership/activation/visibility/pair policy still applies.
        return self.banned_at is None and self.deleted_at is None

    def next_source_version(self) -> int:
        if self.source_version == MAX_LIFECYCLE_SOURCE_VERSION:
            raise ValueError("Lifecycle source version exhausted")
        return self.source_version + 1


@dataclass(frozen=True, slots=True)
class BanRevision:
    id: UUID
    account_id: UUID
    version: int
    banned: bool
    changed_at: datetime
    operator_access: OperatorAccess
    actor_session_id: UUID
    reason: LifecycleReason = field(repr=False)

    def __post_init__(self) -> None:
        require_aware(self.changed_at)
        require_source_version(self.version)
        if not isinstance(self.banned, bool):
            raise ValueError("Ban source requires an explicit boolean flag")
        if not self.operator_access.is_active(self.changed_at):
            raise ValueError("Ban source requires its actual active operator grant")

    @property
    def operation(self) -> LifecycleOperation:
        return LifecycleOperation.BAN if self.banned else LifecycleOperation.UNBAN


@dataclass(frozen=True, slots=True)
class DeletionRevision:
    id: UUID
    account_id: UUID
    version: int
    deleted_at: datetime
    actor_session_id: UUID
    workflow_id: UUID

    def __post_init__(self) -> None:
        require_source_version(self.version)
        require_aware(self.deleted_at)

    @property
    def operation(self) -> LifecycleOperation:
        return LifecycleOperation.DELETE


@dataclass(frozen=True, slots=True)
class BanTransition:
    before: AccountLifecycle
    after: AccountLifecycle
    revision: BanRevision | None

    def __post_init__(self) -> None:
        if self.revision is None:
            if self.before != self.after:
                raise ValueError("No-op ban cannot change flags or invent a source version")
        elif self.after != changed_ban_state(self.before, self.revision):
            raise ValueError("Ban transition differs from its actual immutable source")

    @property
    def changed(self) -> bool:
        return self.revision is not None


@dataclass(frozen=True, slots=True)
class DeletionTransition:
    before: AccountLifecycle
    after: AccountLifecycle
    revision: DeletionRevision

    def __post_init__(self) -> None:
        if self.after != changed_deletion_state(self.before, self.revision):
            raise ValueError("Deletion transition differs from its actual immutable source")


def require_source_version(version: int) -> None:
    if isinstance(version, bool) or not 1 <= version <= MAX_LIFECYCLE_SOURCE_VERSION:
        raise ValueError("Lifecycle source requires a positive bounded actual version")


def changed_ban_state(before: AccountLifecycle, revision: BanRevision) -> AccountLifecycle:
    if revision.account_id != before.account_id or revision.version != before.next_source_version():
        raise ValueError("Ban source differs from its actual account or next source version")
    currently_banned = before.banned_at is not None
    if currently_banned == revision.banned:
        raise ValueError("No-op ban cannot create a new lifecycle source")
    if before.banned_at is not None and revision.changed_at < before.banned_at:
        raise ValueError("Ban change cannot precede the actual current ban")
    return replace(
        before,
        banned_at=revision.changed_at if revision.banned else None,
        source_version=revision.version,
    )


def changed_deletion_state(
    before: AccountLifecycle, revision: DeletionRevision
) -> AccountLifecycle:
    if before.deleted_at is not None:
        raise DeletedLifecycleAccountError
    if revision.account_id != before.account_id or revision.version != before.next_source_version():
        raise ValueError("Deletion source differs from its actual account or next source version")
    if before.banned_at is not None and revision.deleted_at < before.banned_at:
        raise ValueError("Deletion cannot precede the actual current ban")
    return replace(before, deleted_at=revision.deleted_at, source_version=revision.version)


@dataclass(frozen=True, slots=True)
class BanChangeEvidence:
    id: UUID
    at: datetime
    operator_access: OperatorAccess
    actor_session_id: UUID

    def __post_init__(self) -> None:
        require_aware(self.at)
        if not self.operator_access.is_active(self.at):
            raise ValueError("Ban planning requires its actual active operator grant")


def plan_ban_change(
    before: AccountLifecycle,
    *,
    banned: bool,
    evidence: BanChangeEvidence,
    reason: LifecycleReason,
) -> BanTransition:
    if not isinstance(banned, bool):
        raise ValueError("Ban planning requires an explicit boolean flag")
    if (before.banned_at is not None) == banned:
        return BanTransition(before, before, None)
    revision = BanRevision(
        evidence.id,
        before.account_id,
        before.next_source_version(),
        banned,
        evidence.at,
        evidence.operator_access,
        evidence.actor_session_id,
        reason,
    )
    return BanTransition(before, changed_ban_state(before, revision), revision)


def plan_deletion(
    before: AccountLifecycle,
    *,
    change_id: UUID,
    at: datetime,
    actor_session_id: UUID,
    workflow_id: UUID,
) -> DeletionTransition:
    revision = DeletionRevision(
        change_id,
        before.account_id,
        before.next_source_version(),
        at,
        actor_session_id,
        workflow_id,
    )
    return DeletionTransition(before, changed_deletion_state(before, revision), revision)
