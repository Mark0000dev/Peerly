from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from studymate.application.discovery.profiles import DiscoveryProfile
from studymate.application.safety.block_list import BLOCKS_PAGE_SIZE, OwnBlocksPage
from studymate.application.safety.blocks import OwnBlockResult
from studymate.domain.message_reports import MessageImageReport, MessageImageReportContext
from studymate.domain.reports import (
    MAX_REPORT_COMMENT_LENGTH,
    ProfileReport,
    ReportCategory,
    report_comment,
)
from studymate.domain.text import optional_text
from studymate.presentation.study_models import (
    GoalResponse,
    HelpResponse,
    goal_response,
    help_response,
)


class BlockStateResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    person_id: UUID
    blocked: bool
    version: int
    changed_at: datetime | None


class ChangeBlockRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    blocked: bool = Field(strict=True)
    expected_version: int = Field(strict=True, ge=0)
    context_id: UUID | None = None


class PublicPhotoResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    version: int
    display_url: str


class PublicProfileResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: UUID
    version: int
    display_name: str = Field(repr=False)
    about: str | None = Field(repr=False)
    programme: str | None = Field(repr=False)
    year_label: str | None = Field(repr=False)
    languages: tuple[str, ...]
    photo: PublicPhotoResponse
    goal: GoalResponse | None
    help_subjects: HelpResponse | None
    access_context_id: UUID
    own_block: BlockStateResponse


class BlockedPersonResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    block: BlockStateResponse
    display_name: str | None = Field(repr=False)
    deleted: bool


class OwnBlocksResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    people: tuple[BlockedPersonResponse, ...] = Field(max_length=BLOCKS_PAGE_SIZE)
    next_cursor: str | None


class ReportSubmissionBody(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    context_id: UUID
    category: ReportCategory
    comment: str | None = Field(default=None, max_length=MAX_REPORT_COMMENT_LENGTH, repr=False)

    @field_validator("comment")
    @classmethod
    def normalize_comment(cls, value: str | None) -> str | None:
        return optional_text(value, maximum=MAX_REPORT_COMMENT_LENGTH, multiline=True)

    @model_validator(mode="after")
    def require_explanation(self) -> Self:
        report_comment(self.category, self.comment)
        return self


class ProfileReportRequest(ReportSubmissionBody):
    kind: Literal["profile"]


class MessageImageReportRequest(ReportSubmissionBody):
    kind: Literal["message_image"]


type ReportRequest = Annotated[
    ProfileReportRequest | MessageImageReportRequest, Field(discriminator="kind")
]


class ProfileReportReceipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: UUID
    kind: Literal["profile"] = "profile"
    context_id: UUID
    submitted_at: datetime


class MessageImageReportReceipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: UUID
    kind: Literal["message_image"] = "message_image"
    context_id: UUID
    submitted_at: datetime


type ReportReceipt = Annotated[
    ProfileReportReceipt | MessageImageReportReceipt, Field(discriminator="kind")
]


class MessageImageReportContextResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: UUID
    kind: Literal["message_image"] = "message_image"
    conversation_id: UUID
    message_id: UUID
    image_id: UUID
    issued_at: datetime


def message_report_context(value: MessageImageReportContext) -> MessageImageReportContextResponse:
    image = value.source.image
    if image is None:
        raise RuntimeError("Report context lost its actual confirmed image source")
    return MessageImageReportContextResponse(
        id=value.id,
        conversation_id=value.source.conversation_id,
        message_id=value.source.message_id,
        image_id=image.id,
        issued_at=value.issued_at,
    )


def block_response(value: OwnBlockResult) -> BlockStateResponse:
    return BlockStateResponse(
        person_id=value.target_id,
        blocked=value.blocked,
        version=value.version,
        changed_at=value.changed_at,
    )


def profile_response(value: DiscoveryProfile) -> PublicProfileResponse:
    basics = value.profile.basics
    if basics.display_name is None:
        raise RuntimeError("An authorised public profile requires its saved display name")
    return PublicProfileResponse(
        id=value.profile.account_id,
        version=value.profile.version,
        display_name=basics.display_name.value,
        about=basics.about,
        programme=basics.programme,
        year_label=basics.year_label,
        languages=tuple(language.value for language in basics.languages),
        photo=PublicPhotoResponse(
            version=value.photo.version,
            display_url=f"/api/v1/people/{value.profile.account_id}/photo/{value.photo.version}",
        ),
        goal=goal_response(value.goal) if value.goal is not None else None,
        help_subjects=help_response(value.help_subjects)
        if value.help_subjects is not None
        else None,
        access_context_id=value.access_context.id,
        own_block=block_response(value.own_block),
    )


def blocks_response(value: OwnBlocksPage) -> OwnBlocksResponse:
    return OwnBlocksResponse(
        people=tuple(
            BlockedPersonResponse(
                block=block_response(person.block),
                display_name=person.display_name.value if person.display_name is not None else None,
                deleted=person.deleted,
            )
            for person in value.people
        ),
        next_cursor=value.next_cursor,
    )


def report_receipt(value: ProfileReport | MessageImageReport) -> ReportReceipt:
    if isinstance(value, MessageImageReport):
        return MessageImageReportReceipt(
            id=value.id, context_id=value.context.id, submitted_at=value.submitted_at
        )
    return ProfileReportReceipt(
        id=value.id, context_id=value.context.id, submitted_at=value.submitted_at
    )
