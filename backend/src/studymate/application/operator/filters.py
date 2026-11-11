from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from studymate.domain.identity import StudentEmail
from studymate.domain.membership import GOOGLE_ISSUER, MAX_SUBJECT_LENGTH
from studymate.domain.text import plain_text
from studymate.domain.time import require_aware


class OperatorAccountLifecycle(StrEnum):
    ALL = "all"
    ACTIVE = "active"
    BANNED = "banned"
    DELETED = "deleted"


@dataclass(frozen=True, slots=True)
class OperatorAccountFilters:
    account_id: UUID | None = None
    google_link_id: UUID | None = None
    google_issuer: str | None = None
    google_subject: str | None = field(default=None, repr=False)
    institutional_email: StudentEmail | None = field(default=None, repr=False)
    name: str | None = field(default=None, repr=False)
    lifecycle: OperatorAccountLifecycle = OperatorAccountLifecycle.ALL
    hidden: bool | None = None
    created_from: datetime | None = None
    created_before: datetime | None = None

    def __post_init__(self) -> None:
        if self.google_issuer is not None and self.google_issuer != GOOGLE_ISSUER:
            raise ValueError("Only the actual stored Google issuer is supported")
        if self.google_subject is not None and (
            not self.google_subject
            or not self.google_subject.isascii()
            or len(self.google_subject) > MAX_SUBJECT_LENGTH
        ):
            raise ValueError("Stored Google subject search must be bounded")
        if self.google_subject is not None or self.google_link_id is not None:
            object.__setattr__(self, "google_issuer", GOOGLE_ISSUER)
        if self.name is not None:
            object.__setattr__(
                self, "name", plain_text(self.name, minimum=1, maximum=50, collapse_spaces=True)
            )
        if self.hidden is not None and not isinstance(self.hidden, bool):
            raise ValueError("Hidden filter must be an explicit boolean")
        for at in (self.created_from, self.created_before):
            if at is not None:
                require_aware(at)
        if (
            self.created_from is not None
            and self.created_before is not None
            and self.created_from >= self.created_before
        ):
            raise ValueError("Created-time search interval must be nonempty and ordered")

    def fingerprint_parts(self) -> tuple[str, ...]:
        return (
            "operator.accounts.filters.v1",
            str(self.account_id or ""),
            str(self.google_link_id or ""),
            self.google_issuer or "",
            self.google_subject or "",
            self.institutional_email.value if self.institutional_email is not None else "",
            self.name or "",
            self.lifecycle.value,
            "any" if self.hidden is None else str(self.hidden),
            self.created_from.astimezone(UTC).isoformat() if self.created_from is not None else "",
            self.created_before.astimezone(UTC).isoformat()
            if self.created_before is not None
            else "",
        )
