from dataclasses import dataclass

from studymate.application.identity.sessions import (
    SessionCredential,
    SessionHasher,
    require_verified_student,
)
from studymate.application.profiles.basics import ProfileUnitOfWork
from studymate.domain.language_data import LANGUAGE_CHOICES
from studymate.domain.profiles import (
    MAX_DISPLAY_NAME_LENGTH,
    MAX_LANGUAGES,
    MIN_DISPLAY_NAME_LENGTH,
)


@dataclass(frozen=True, slots=True)
class ProfileLanguageOption:
    code: str
    label: str


@dataclass(frozen=True, slots=True)
class ProfileReferenceData:
    languages: tuple[ProfileLanguageOption, ...]
    max_languages: int = MAX_LANGUAGES
    min_display_name_length: int = MIN_DISPLAY_NAME_LENGTH
    max_display_name_length: int = MAX_DISPLAY_NAME_LENGTH
    university: str = "APU Malaysia"


@dataclass(frozen=True, slots=True)
class ReadProfileReferenceData:
    unit_of_work: ProfileUnitOfWork
    hasher: SessionHasher

    async def __call__(self, credential: SessionCredential) -> ProfileReferenceData:
        async with self.unit_of_work.transaction() as transaction:
            await require_verified_student(transaction, await self.hasher.digest(credential))
        return ProfileReferenceData(
            tuple(ProfileLanguageOption(code, label) for code, label in LANGUAGE_CHOICES)
        )
