import re
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from studymate.domain.time import require_aware


class PolicyKind(StrEnum):
    TERMS = "terms"
    PRIVACY = "privacy"


@dataclass(frozen=True, slots=True)
class PolicyVersion:
    value: str

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", self.value):
            raise ValueError("Invalid policy document version")


@dataclass(frozen=True, slots=True)
class PolicyReference:
    id: UUID
    kind: PolicyKind
    version: PolicyVersion
    published_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.published_at)


@dataclass(frozen=True, slots=True)
class PublishedPolicy:
    reference: PolicyReference
    title: str
    content: str = field(repr=False)

    def __post_init__(self) -> None:
        if not self.title.strip() or not self.content.strip():
            raise ValueError("Published policy documents must have actual content")


class RegistrationSurface(StrEnum):
    ONBOARDING_COMPLETION = "onboarding_completion"


@dataclass(frozen=True, slots=True)
class RegistrationContext:
    id: UUID
    account_id: UUID
    session_id: UUID
    terms: PolicyReference
    privacy: PolicyReference
    notice_text: str
    created_at: datetime
    expires_at: datetime
    completed_at: datetime | None = None
    surface: RegistrationSurface = RegistrationSurface.ONBOARDING_COMPLETION

    def __post_init__(self) -> None:
        require_aware(self.created_at)
        require_aware(self.expires_at)
        if self.terms.kind != PolicyKind.TERMS or self.privacy.kind != PolicyKind.PRIVACY:
            raise ValueError("Registration document kinds do not match")
        if self.terms.published_at > self.created_at or self.privacy.published_at > self.created_at:
            raise ValueError("Registration cannot reference unpublished documents")
        if self.expires_at <= self.created_at or not self.notice_text.strip():
            raise ValueError("Registration context requires a notice and valid deadline")
        if self.completed_at is not None:
            require_aware(self.completed_at)
            if self.completed_at < self.created_at:
                raise ValueError("Registration completion precedes context issuance")

    def can_complete(self, account_id: UUID, session_id: UUID, at: datetime) -> bool:
        require_aware(at)
        return (
            self.account_id == account_id
            and self.session_id == session_id
            and self.completed_at is None
            and self.created_at <= at < self.expires_at
        )

    def complete(self, account_id: UUID, session_id: UUID, at: datetime) -> "RegistrationContext":
        if not self.can_complete(account_id, session_id, at):
            raise ValueError("Registration context is unavailable")
        return replace(self, completed_at=at)


@dataclass(frozen=True, slots=True)
class RegistrationReceipt:
    id: UUID
    account_id: UUID
    context: RegistrationContext
    registered_at: datetime
    intent_key: str = field(repr=False)

    def __post_init__(self) -> None:
        require_aware(self.registered_at)
        if (
            self.account_id != self.context.account_id
            or self.context.completed_at != self.registered_at
        ):
            raise ValueError("Registration receipt must reference its actual completion")
