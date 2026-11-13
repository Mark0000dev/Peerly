"""Bounded tagged options, exact advisory provenance and editable ordinary message text."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from studymate.application.requests.response_options_data import (
    MAX_RESPONSE_OPTIONS,
    LearningTooResponseOption,
    RequestResponseOptions,
    ResponseChoice,
    SwapResponseOption,
)
from studymate.domain.messaging import MAX_MESSAGE_LENGTH


class ResponseOptionsModel(BaseModel):
    model_config = ConfigDict(
        frozen=True, extra="forbid", json_schema_serialization_defaults_required=True
    )


class ResponseOptionsQuery(ResponseOptionsModel):
    pass


class ResponseGoalSourceResponse(ResponseOptionsModel):
    id: UUID
    version: int = Field(ge=1)
    subject_id: UUID
    subject_label: str = Field(repr=False)
    topic: str | None = Field(repr=False)


class ResponsePeerHelpSourceResponse(ResponseOptionsModel):
    account_id: UUID
    version: int = Field(ge=1)
    subject_id: UUID
    subject_label: str = Field(repr=False)


class LearningTooOptionResponse(ResponseOptionsModel):
    kind: Literal["learning_too"] = "learning_too"
    suggested_text: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH, repr=False)
    own_goal: ResponseGoalSourceResponse = Field(repr=False)


class SwapOptionResponse(ResponseOptionsModel):
    kind: Literal["swap"] = "swap"
    suggested_text: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH, repr=False)
    own_goal: ResponseGoalSourceResponse = Field(repr=False)
    peer_help: ResponsePeerHelpSourceResponse = Field(repr=False)


class WriteOwnOptionResponse(ResponseOptionsModel):
    kind: Literal["write_my_own"] = "write_my_own"
    suggested_text: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH, repr=False)


type ResponseOptionResponse = Annotated[
    LearningTooOptionResponse | SwapOptionResponse | WriteOwnOptionResponse,
    Field(discriminator="kind"),
]


class RequestResponseOptionsResponse(ResponseOptionsModel):
    request_id: UUID
    request_version: int = Field(ge=1)
    person_id: UUID
    observed_at: AwareDatetime
    request_expires_at: AwareDatetime
    default_choice: ResponseChoice
    options: tuple[ResponseOptionResponse, ...] = Field(
        min_length=1, max_length=MAX_RESPONSE_OPTIONS, repr=False
    )


def response_options_response(value: RequestResponseOptions) -> RequestResponseOptionsResponse:
    options: list[ResponseOptionResponse] = []
    for option in value.options:
        if isinstance(option, (LearningTooResponseOption, SwapResponseOption)):
            source = option.own_goal
            goal = ResponseGoalSourceResponse(
                id=source.id,
                version=source.version,
                subject_id=source.subject_id,
                subject_label=source.subject_label,
                topic=source.topic,
            )
            if isinstance(option, LearningTooResponseOption):
                options.append(
                    LearningTooOptionResponse(suggested_text=option.suggested_text, own_goal=goal)
                )
            else:
                peer = option.peer_help
                options.append(
                    SwapOptionResponse(
                        suggested_text=option.suggested_text,
                        own_goal=goal,
                        peer_help=ResponsePeerHelpSourceResponse(
                            account_id=peer.account_id,
                            version=peer.version,
                            subject_id=peer.subject_id,
                            subject_label=peer.subject_label,
                        ),
                    )
                )
        else:
            options.append(WriteOwnOptionResponse(suggested_text=option.suggested_text))
    return RequestResponseOptionsResponse(
        request_id=value.request_id,
        request_version=value.request_version,
        person_id=value.person_id,
        observed_at=value.observed_at,
        request_expires_at=value.request_expires_at,
        default_choice=value.default_choice,
        options=tuple(options),
    )
