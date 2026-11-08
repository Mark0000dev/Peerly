from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from studymate.domain.discovery import DiscoveryMode
from studymate.domain.requests.context import MAX_REQUEST_TEXT, RequestText


class PreviewRequestBody(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    person_id: UUID
    mode: DiscoveryMode


class SendRequestBody(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    person_id: UUID
    preview_id: UUID
    text: str = Field(min_length=1, max_length=MAX_REQUEST_TEXT, repr=False)
    note: str | None = Field(default=None, max_length=MAX_REQUEST_TEXT, repr=False)

    def message(self) -> RequestText:
        return RequestText(self.text, self.note)

    @model_validator(mode="after")
    def valid_message(self) -> Self:
        self.message()
        return self


class RequestActionBody(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    person_id: UUID
    expected_version: int = Field(strict=True, ge=1)


class ViewRequestBody(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    disclosure_id: UUID
