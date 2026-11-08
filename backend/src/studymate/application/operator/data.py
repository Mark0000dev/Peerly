from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from studymate.application.profiles.goals import SavedGoal
from studymate.application.profiles.help_subjects import SavedHelpSubjects
from studymate.domain.discovery_freshness import DiscoveryExposure
from studymate.domain.media import PhotoRevision
from studymate.domain.membership import GOOGLE_ISSUER, MAX_SUBJECT_LENGTH, Membership
from studymate.domain.onboarding import ProfileLifecycle
from studymate.domain.profiles import DisplayName, ProfileRevision
from studymate.domain.registration import PolicyKind, PolicyReference, RegistrationSurface
from studymate.domain.time import require_aware


@dataclass(frozen=True, slots=True)
class StoredGoogleLink:
    """Stored verified-link facts, not a fresh provider assertion or email claim."""

    id: UUID
    account_id: UUID
    issuer: str
    subject: str = field(repr=False)
    created_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.created_at)
        if (
            self.issuer != GOOGLE_ISSUER
            or not self.subject
            or len(self.subject) > MAX_SUBJECT_LENGTH
            or not self.subject.isascii()
        ):
            raise ValueError("Stored Google link has invalid source identifiers")


@dataclass(frozen=True, slots=True)
class OperatorMembershipSnapshot:
    account_id: UUID
    membership: Membership = field(repr=False)


@dataclass(frozen=True, slots=True)
class OperatorAccountSummary:
    account_id: UUID
    created_at: datetime
    banned_at: datetime | None
    deleted_at: datetime | None
    google_link: StoredGoogleLink | None = field(repr=False)
    membership: OperatorMembershipSnapshot | None = field(repr=False)
    profile_version: int | None
    display_name: DisplayName | None = field(repr=False)
    hidden_at: datetime | None

    def __post_init__(self) -> None:
        require_aware(self.created_at)
        for value in (self.banned_at, self.deleted_at, self.hidden_at):
            if value is not None:
                require_aware(value)
        if self.google_link is not None and self.google_link.account_id != self.account_id:
            raise ValueError("Google link belongs to another account")
        if self.membership is not None and self.membership.account_id != self.account_id:
            raise ValueError("Membership belongs to another account")
        if self.profile_version is not None and (
            isinstance(self.profile_version, bool) or self.profile_version < 1
        ):
            raise ValueError("Stored profile revision must be positive")
        if self.profile_version is None and self.display_name is not None:
            raise ValueError("Name must reference an actual stored profile revision")


@dataclass(frozen=True, slots=True)
class OperatorRegistrationSnapshot:
    id: UUID
    account_id: UUID
    context_id: UUID
    registered_at: datetime
    terms: PolicyReference
    privacy: PolicyReference
    notice_text: str = field(repr=False)
    surface: RegistrationSurface

    def __post_init__(self) -> None:
        require_aware(self.registered_at)
        if self.terms.kind != PolicyKind.TERMS or self.privacy.kind != PolicyKind.PRIVACY:
            raise ValueError("Stored registration document references do not match their kinds")
        if not self.notice_text.strip():
            raise ValueError("Stored registration must retain its actual notice")


class OperatorAccountLinkKind(StrEnum):
    GOOGLE_IDENTITY = "google_identity"
    PROFILE_REVISION = "profile_revision"
    PHOTO_REVISION = "photo_revision"
    GOAL_REVISION = "goal_revision"
    HELP_REVISION = "help_revision"
    REGISTRATION_RECEIPT = "registration_receipt"


@dataclass(frozen=True, slots=True)
class OperatorAccountLink:
    kind: OperatorAccountLinkKind
    id: UUID
    version: int | None = None


@dataclass(frozen=True, slots=True)
class OperatorAccountDetail:
    account: OperatorAccountSummary = field(repr=False)
    profile: ProfileRevision | None = field(repr=False)
    photo: PhotoRevision | None
    goal: SavedGoal | None = field(repr=False)
    help_subjects: SavedHelpSubjects | None = field(repr=False)
    lifecycle: ProfileLifecycle | None
    exposure: DiscoveryExposure | None
    registration: OperatorRegistrationSnapshot | None = field(repr=False)

    def __post_init__(self) -> None:
        account_id = self.account.account_id
        for value in (self.profile, self.photo, self.lifecycle, self.exposure, self.registration):
            if value is not None and value.account_id != account_id:
                raise ValueError("Operator account detail contains a foreign source")
        if self.goal is not None and self.goal.goal.account_id != account_id:
            raise ValueError("Operator account detail contains a foreign goal")
        if self.help_subjects is not None and self.help_subjects.revision.account_id != account_id:
            raise ValueError("Operator account detail contains foreign help declarations")
        if (
            self.profile.version if self.profile is not None else None
        ) != self.account.profile_version:
            raise ValueError("Operator account profile must match its actual source revision")
        if (
            self.profile is not None
            and self.profile.basics.display_name != self.account.display_name
        ):
            raise ValueError("Operator account name must match its actual stored profile")

    @property
    def links(self) -> tuple[OperatorAccountLink, ...]:
        refs: list[OperatorAccountLink] = []
        if self.account.google_link is not None:
            refs.append(
                OperatorAccountLink(
                    OperatorAccountLinkKind.GOOGLE_IDENTITY, self.account.google_link.id
                )
            )
        if self.profile is not None:
            refs.append(
                OperatorAccountLink(
                    OperatorAccountLinkKind.PROFILE_REVISION,
                    self.profile.account_id,
                    self.profile.version,
                )
            )
        if self.photo is not None:
            refs.append(
                OperatorAccountLink(
                    OperatorAccountLinkKind.PHOTO_REVISION,
                    self.photo.account_id,
                    self.photo.version,
                )
            )
        if self.goal is not None:
            refs.append(
                OperatorAccountLink(
                    OperatorAccountLinkKind.GOAL_REVISION, self.goal.goal.id, self.goal.goal.version
                )
            )
        if self.help_subjects is not None:
            refs.append(
                OperatorAccountLink(
                    OperatorAccountLinkKind.HELP_REVISION,
                    self.help_subjects.revision.account_id,
                    self.help_subjects.revision.version,
                )
            )
        if self.registration is not None:
            refs.append(
                OperatorAccountLink(
                    OperatorAccountLinkKind.REGISTRATION_RECEIPT, self.registration.id
                )
            )
        return tuple(refs)
