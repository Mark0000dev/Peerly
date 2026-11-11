from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from unicodedata import category
from uuid import UUID

from studymate.domain.time import require_aware

MAX_REPLY_LENGTH = 254
MAX_MESSAGE_LENGTH = 4000
MAX_DETAILS_LENGTH = 2000


class SupportTopic(StrEnum):
    CANNOT_SIGN_IN = "cannot_sign_in"
    EMAIL_NOT_ACCEPTED = "email_not_accepted"
    CODE_NOT_ARRIVING = "code_not_arriving"
    EMAIL_ALREADY_IN_USE = "email_already_in_use"
    DELETED_ACCOUNT = "deleted_account"
    OTHER = "other"


class SupportStatus(StrEnum):
    RECEIVED = "received"
    IN_REVIEW = "in_review"
    RESOLVED = "resolved"


@dataclass(frozen=True, slots=True)
class SupportContent:
    topic: SupportTopic
    reply_address: str = field(repr=False)
    message: str = field(repr=False)
    details: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        address = self.reply_address
        if (
            len(address) > MAX_REPLY_LENGTH
            or address != address.strip()
            or address.count("@") != 1
            or any(c.isspace() or category(c) in {"Cs", "Cc"} for c in address)
            or not all(address.split("@"))
            or "." not in address.split("@")[1]
        ):
            raise ValueError("A bounded reply address is required")
        if not self.message.strip() or len(self.message) > MAX_MESSAGE_LENGTH:
            raise ValueError("Support message must contain 1 to 4000 characters")
        if self.details is not None and (
            not self.details.strip() or len(self.details) > MAX_DETAILS_LENGTH
        ):
            raise ValueError("Optional support details must contain 1 to 2000 characters")
        for value in (self.message, self.details or ""):
            if any(
                category(c) == "Cs" or (category(c) == "Cc" and c not in "\n\r\t") for c in value
            ):
                raise ValueError("Support text contains unsupported control characters")


@dataclass(frozen=True, slots=True)
class SupportReceipt:
    case_id: UUID
    status: SupportStatus
    version: int
    received_at: datetime
    changed_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.received_at)
        require_aware(self.changed_at)
        if isinstance(self.version, bool) or self.version < 1 or self.changed_at < self.received_at:
            raise ValueError("Support receipt requires an actual ordered revision")
