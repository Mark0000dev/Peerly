from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from studymate.application.discovery.deck import (
    DISCOVERY_PAGE_SIZE,
    DiscoveryCard,
    DiscoveryEmptyReason,
    DiscoveryPage,
)
from studymate.domain.discovery import DiscoveryMode, RelevanceReason
from studymate.domain.discovery_context import DiscoveryContext, DiscoveryScope
from studymate.domain.discovery_passes import PrivatePassRevision
from studymate.presentation.people_models import PublicPhotoResponse


class _GoalContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    goal_id: UUID
    goal_version: int = Field(strict=True, ge=1)


class FindHelpContext(_GoalContext):
    mode: Literal["find_help"]


class StudyTogetherContext(_GoalContext):
    mode: Literal["study_together"]


class OfferHelpContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    mode: Literal["offer_help"]
    help_version: int = Field(strict=True, ge=1)


type DiscoveryContextBody = Annotated[
    FindHelpContext | OfferHelpContext | StudyTogetherContext, Field(discriminator="mode")
]


class ChangePassRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    context: DiscoveryContextBody
    passed: bool = Field(strict=True)
    expected_version: int = Field(strict=True, ge=0)
    undo: bool = Field(default=False, strict=True)

    @model_validator(mode="after")
    def require_reconsideration(self) -> Self:
        if self.undo and self.passed:
            raise ValueError("Undo only reconsiders a private pass")
        return self


class PrivatePassResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    person_id: UUID
    passed: bool
    version: int
    changed_at: datetime | None


class DiscoveryRelevanceResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    reason: RelevanceReason
    subject_id: UUID
    subject_label: str = Field(repr=False)
    topic: str | None = Field(repr=False)
    same_topic: bool
    reciprocal_subject_id: UUID | None
    reciprocal_subject_label: str | None = Field(repr=False)


class DiscoveryCardResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: UUID
    version: int
    display_name: str = Field(repr=False)
    about: str | None = Field(repr=False)
    photo: PublicPhotoResponse
    relevance: DiscoveryRelevanceResponse
    own_pass: PrivatePassResponse


class DiscoveryPageResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    context: DiscoveryContextBody | None
    people: tuple[DiscoveryCardResponse, ...] = Field(max_length=DISCOVERY_PAGE_SIZE)
    next_cursor: str | None
    empty_reason: DiscoveryEmptyReason | None
    undo_pass: PrivatePassResponse | None


def scope_value(value: DiscoveryContextBody) -> DiscoveryScope:
    if isinstance(value, OfferHelpContext):
        return DiscoveryScope(DiscoveryMode.OFFER_HELP, None, None, value.help_version)
    return DiscoveryScope(DiscoveryMode(value.mode), value.goal_id, value.goal_version, None)


def context_response(value: DiscoveryContext) -> DiscoveryContextBody:
    if value.mode == DiscoveryMode.OFFER_HELP:
        if value.help_version is None:
            raise RuntimeError("Offer-help context lacks its actual saved revision")
        return OfferHelpContext(mode="offer_help", help_version=value.help_version)
    if value.goal_id is None or value.goal_version is None:
        raise RuntimeError("Learning context lacks its actual saved goal")
    if value.mode == DiscoveryMode.FIND_HELP:
        return FindHelpContext(
            mode="find_help", goal_id=value.goal_id, goal_version=value.goal_version
        )
    return StudyTogetherContext(
        mode="study_together", goal_id=value.goal_id, goal_version=value.goal_version
    )


def pass_response(value: PrivatePassRevision | None, target_id: UUID) -> PrivatePassResponse:
    return PrivatePassResponse(
        person_id=target_id,
        passed=value.passed if value is not None else False,
        version=value.version if value is not None else 0,
        changed_at=value.changed_at if value is not None else None,
    )


def _subject(card: DiscoveryCard, subject_id: UUID) -> str:
    if card.goal is not None and card.goal.goal.content.canonical_subject_id == subject_id:
        return card.goal.subject_label
    if card.help_subjects is not None:
        for item, label in zip(
            card.help_subjects.revision.subjects.values, card.help_subjects.labels, strict=True
        ):
            if item.subject_id == subject_id:
                return label
    raise RuntimeError("Discovery explanation lacks its declared subject source")


def _topic(card: DiscoveryCard) -> str | None:
    if card.match.reason == RelevanceReason.CAN_HELP:
        if card.help_subjects is not None:
            return next(
                (
                    item.topic_note
                    for item in card.help_subjects.revision.subjects.values
                    if item.subject_id == card.match.subject_id
                ),
                None,
            )
        return None
    return card.goal.goal.content.topic if card.goal is not None else None


def _card_response(card: DiscoveryCard) -> DiscoveryCardResponse:
    if card.profile.basics.display_name is None:
        raise RuntimeError("Discovery card lacks its saved display name")
    peer_id = card.profile.account_id
    reciprocal = card.match.reciprocal_subject_id
    return DiscoveryCardResponse(
        id=peer_id,
        version=card.profile.version,
        display_name=card.profile.basics.display_name.value,
        about=card.profile.basics.about,
        photo=PublicPhotoResponse(
            version=card.photo.version,
            display_url=f"/api/v1/people/{peer_id}/photo/{card.photo.version}",
        ),
        relevance=DiscoveryRelevanceResponse(
            reason=card.match.reason,
            subject_id=card.match.subject_id,
            subject_label=_subject(card, card.match.subject_id),
            topic=_topic(card),
            same_topic=card.match.same_topic,
            reciprocal_subject_id=reciprocal,
            reciprocal_subject_label=_subject(card, reciprocal) if reciprocal is not None else None,
        ),
        own_pass=pass_response(card.own_pass, peer_id),
    )


def page_response(value: DiscoveryPage) -> DiscoveryPageResponse:
    return DiscoveryPageResponse(
        context=context_response(value.context) if value.context is not None else None,
        people=tuple(_card_response(card) for card in value.people),
        next_cursor=value.next_cursor,
        empty_reason=value.empty_reason,
        undo_pass=pass_response(value.undo_pass, value.undo_pass.target_id)
        if value.undo_pass is not None
        else None,
    )
