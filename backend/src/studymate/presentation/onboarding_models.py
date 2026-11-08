from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from studymate.application.profiles.onboarding import OnboardingStatus
from studymate.domain.onboarding import ProfileLifecycle
from studymate.domain.profile_readiness import OnboardingRequirement, RestoreRequirement


class ChangeVisibilityRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    hidden: bool = Field(strict=True)
    expected_version: int = Field(strict=True, ge=1)


class ProfileVisibilityResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    version: int
    hidden: bool
    completed_at: datetime
    hidden_at: datetime | None
    changed_at: datetime


class ProfileCapabilitiesResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    can_manage_profile: bool
    can_complete_setup: bool
    can_complete_registration: bool
    can_discover: bool
    can_make_new_contacts: bool
    can_access_existing_chats: bool
    can_hide_profile: bool
    can_restore_profile: bool


class DiscoveryExposureResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    paused: bool
    can_confirm: bool
    requirements: tuple[RestoreRequirement, ...]


class OnboardingStatusResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    registered: bool
    setup_complete: bool
    setup_requirements: tuple[OnboardingRequirement, ...]
    restore_requirements: tuple[RestoreRequirement, ...]
    capabilities: ProfileCapabilitiesResponse
    visibility: ProfileVisibilityResponse | None
    discovery_exposure: DiscoveryExposureResponse | None


def visibility_response(lifecycle: ProfileLifecycle) -> ProfileVisibilityResponse:
    return ProfileVisibilityResponse(
        version=lifecycle.visibility_version,
        hidden=lifecycle.hidden,
        completed_at=lifecycle.completed_at,
        hidden_at=lifecycle.hidden_at,
        changed_at=lifecycle.changed_at,
    )


def onboarding_response(status: OnboardingStatus) -> OnboardingStatusResponse:
    capabilities = status.capabilities
    return OnboardingStatusResponse(
        registered=status.registered,
        setup_complete=status.setup_complete,
        setup_requirements=capabilities.setup_requirements,
        restore_requirements=capabilities.restore_requirements,
        capabilities=ProfileCapabilitiesResponse(
            can_manage_profile=capabilities.can_manage_profile,
            can_complete_setup=capabilities.can_complete_setup,
            can_complete_registration=capabilities.can_complete_registration,
            can_discover=capabilities.can_discover,
            can_make_new_contacts=capabilities.can_make_new_contacts,
            can_access_existing_chats=capabilities.can_access_existing_chats,
            can_hide_profile=capabilities.can_hide_profile,
            can_restore_profile=capabilities.can_restore_profile,
        ),
        visibility=visibility_response(status.lifecycle) if status.lifecycle is not None else None,
        discovery_exposure=DiscoveryExposureResponse(
            paused=status.discovery_exposure.paused,
            can_confirm=status.discovery_exposure.can_confirm,
            requirements=status.discovery_exposure.requirements,
        )
        if status.discovery_exposure is not None
        else None,
    )
