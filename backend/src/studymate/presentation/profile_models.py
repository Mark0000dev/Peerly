from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from studymate.domain.profiles import (
    MAX_ABOUT_LENGTH,
    MAX_DISPLAY_NAME_LENGTH,
    MAX_LANGUAGES,
    MAX_PROGRAMME_LENGTH,
    MAX_YEAR_LABEL_LENGTH,
    MIN_DISPLAY_NAME_LENGTH,
    DisplayName,
    LanguageCode,
    OnboardingTask,
    ProfileRevision,
)
from studymate.domain.text import optional_text


def _optional(value: object, maximum: int, *, multiline: bool = False) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("A plain-text value is required")
    return optional_text(value, maximum=maximum, multiline=multiline)


class SaveProfileRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    display_name: str | None = Field(
        default=None,
        min_length=MIN_DISPLAY_NAME_LENGTH,
        max_length=MAX_DISPLAY_NAME_LENGTH,
        repr=False,
    )
    about: str | None = Field(default=None, max_length=MAX_ABOUT_LENGTH, repr=False)
    programme: str | None = Field(default=None, max_length=MAX_PROGRAMME_LENGTH, repr=False)
    year_label: str | None = Field(default=None, max_length=MAX_YEAR_LABEL_LENGTH, repr=False)
    languages: tuple[str, ...] = Field(default=(), max_length=MAX_LANGUAGES)
    task: OnboardingTask = OnboardingTask.FIND_HELP
    expected_version: int = Field(strict=True, ge=0)

    @field_validator("display_name", mode="before")
    @classmethod
    def normalize_name(cls, value: object) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("A display name must be plain text")
        return DisplayName(value).value

    @field_validator("about", mode="before")
    @classmethod
    def normalize_about(cls, value: object) -> str | None:
        return _optional(value, MAX_ABOUT_LENGTH, multiline=True)

    @field_validator("programme", mode="before")
    @classmethod
    def normalize_programme(cls, value: object) -> str | None:
        return _optional(value, MAX_PROGRAMME_LENGTH)

    @field_validator("year_label", mode="before")
    @classmethod
    def normalize_year(cls, value: object) -> str | None:
        return _optional(value, MAX_YEAR_LABEL_LENGTH)

    @field_validator("languages")
    @classmethod
    def normalize_languages(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        selected = tuple(LanguageCode(value).value for value in values)
        if len(set(selected)) != len(selected):
            raise ValueError("Language selections must be distinct")
        return selected


class ProfileRevisionResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    version: int
    display_name: str | None = Field(repr=False)
    about: str | None = Field(repr=False)
    programme: str | None = Field(repr=False)
    year_label: str | None = Field(repr=False)
    languages: tuple[str, ...]
    task: OnboardingTask
    saved_at: datetime


class CurrentPhotoResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    upload_id: UUID
    version: int
    display_url: str


class OwnProfileResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    profile: ProfileRevisionResponse | None
    photo: CurrentPhotoResponse | None


class LanguageOptionResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    code: str
    label: str


class ProfileReferenceResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    languages: tuple[LanguageOptionResponse, ...]
    max_languages: int
    min_display_name_length: int
    max_display_name_length: int
    university: str


def revision_response(value: ProfileRevision) -> ProfileRevisionResponse:
    basics = value.basics
    return ProfileRevisionResponse(
        version=value.version,
        display_name=basics.display_name.value if basics.display_name is not None else None,
        about=basics.about,
        programme=basics.programme,
        year_label=basics.year_label,
        languages=tuple(language.value for language in basics.languages),
        task=value.task,
        saved_at=value.saved_at,
    )
