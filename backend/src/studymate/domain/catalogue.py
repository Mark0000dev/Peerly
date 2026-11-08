"""Authored reference subjects; names/aliases never auto-map a student's custom choice."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from studymate.domain.text import plain_text
from studymate.domain.time import require_aware

MAX_SUBJECT_LABEL = 80
MAX_SUBJECT_ALIASES = 20


def subject_label(value: str) -> str:
    return plain_text(value, minimum=1, maximum=MAX_SUBJECT_LABEL, collapse_spaces=True)


def subject_key(value: str) -> str:
    return subject_label(value).casefold()


@dataclass(frozen=True, slots=True)
class Subject:
    id: UUID
    name: str = field(repr=False)
    aliases: tuple[str, ...] = field(repr=False)
    created_at: datetime
    archived_at: datetime | None = None

    def __post_init__(self) -> None:
        require_aware(self.created_at)
        canonical = subject_label(self.name)
        aliases = tuple(subject_label(alias) for alias in self.aliases)
        keys = tuple(subject_key(alias) for alias in aliases)
        if (
            len(aliases) > MAX_SUBJECT_ALIASES
            or len(set(keys)) != len(keys)
            or subject_key(canonical) in keys
        ):
            raise ValueError(
                "Subject aliases must be distinct, bounded and different from the name"
            )
        if self.archived_at is not None:
            require_aware(self.archived_at)
            if self.archived_at < self.created_at:
                raise ValueError("Subject archival cannot precede creation")
        object.__setattr__(self, "name", canonical)
        object.__setattr__(self, "aliases", aliases)

    @property
    def selectable(self) -> bool:
        return self.archived_at is None
