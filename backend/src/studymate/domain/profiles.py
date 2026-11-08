"""Private saved profile basics; technical/photo/publication state is separate."""

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from studymate.domain.text import optional_text, plain_text
from studymate.domain.time import require_aware

MAX_DISPLAY_NAME_LENGTH = 50
MIN_DISPLAY_NAME_LENGTH = 2
MAX_LANGUAGES = 5
MAX_ABOUT_LENGTH = 160
MAX_PROGRAMME_LENGTH = 80
MAX_YEAR_LABEL_LENGTH = 32
MAX_LANGUAGE_CODE_LENGTH = 35


class OnboardingTask(StrEnum):
    FIND_HELP = "find_help"
    OFFER_HELP = "offer_help"


@dataclass(frozen=True, slots=True)
class DisplayName:
    value: str = field(repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "value",
            plain_text(
                self.value,
                minimum=MIN_DISPLAY_NAME_LENGTH,
                maximum=MAX_DISPLAY_NAME_LENGTH,
                collapse_spaces=True,
            ),
        )


@dataclass(frozen=True, slots=True)
class LanguageCode:
    """A bounded selection key; application reference data validates support."""

    value: str

    def __post_init__(self) -> None:
        canonical = self.value.strip().lower()
        if (
            len(canonical) > MAX_LANGUAGE_CODE_LENGTH
            or re.fullmatch(r"[a-z]{2,3}(?:-[a-z0-9]{2,8})*", canonical) is None
        ):
            raise ValueError("Language selection key is invalid")
        object.__setattr__(self, "value", canonical)


@dataclass(frozen=True, slots=True)
class ProfileBasics:
    display_name: DisplayName | None = None
    about: str | None = field(default=None, repr=False)
    programme: str | None = field(default=None, repr=False)
    year_label: str | None = field(default=None, repr=False)
    languages: tuple[LanguageCode, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "about", optional_text(self.about, maximum=MAX_ABOUT_LENGTH, multiline=True)
        )
        object.__setattr__(
            self, "programme", optional_text(self.programme, maximum=MAX_PROGRAMME_LENGTH)
        )
        object.__setattr__(
            self, "year_label", optional_text(self.year_label, maximum=MAX_YEAR_LABEL_LENGTH)
        )
        if len(self.languages) > MAX_LANGUAGES or len(set(self.languages)) != len(self.languages):
            raise ValueError("Language selections must be distinct and within the allowed maximum")


@dataclass(frozen=True, slots=True)
class ProfileRevision:
    account_id: UUID
    version: int
    basics: ProfileBasics = field(repr=False)
    task: OnboardingTask
    saved_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.saved_at)
        if isinstance(self.version, bool) or self.version < 1:
            raise ValueError("Profile revision must be a positive integer")
