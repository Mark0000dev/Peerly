"""Current advisory source facts; never a request mutation or competency claim."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from uuid import UUID

MAX_RESPONSE_OPTIONS = 3

type ResponseChoice = Literal["learning_too", "swap", "write_my_own"]


@dataclass(frozen=True, slots=True)
class ResponseGoalSource:
    id: UUID
    version: int
    subject_id: UUID
    subject_label: str = field(repr=False)
    topic: str | None = field(repr=False)


@dataclass(frozen=True, slots=True)
class ResponsePeerHelpSource:
    account_id: UUID
    version: int
    subject_id: UUID
    subject_label: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class LearningTooResponseOption:
    suggested_text: str = field(repr=False)
    own_goal: ResponseGoalSource = field(repr=False)
    kind: Literal["learning_too"] = field(default="learning_too", init=False)


@dataclass(frozen=True, slots=True)
class SwapResponseOption:
    suggested_text: str = field(repr=False)
    own_goal: ResponseGoalSource = field(repr=False)
    peer_help: ResponsePeerHelpSource = field(repr=False)
    kind: Literal["swap"] = field(default="swap", init=False)


@dataclass(frozen=True, slots=True)
class WriteOwnResponseOption:
    suggested_text: str = field(repr=False)
    kind: Literal["write_my_own"] = field(default="write_my_own", init=False)


type RequestResponseOption = LearningTooResponseOption | SwapResponseOption | WriteOwnResponseOption


@dataclass(frozen=True, slots=True)
class RequestResponseOptions:
    request_id: UUID
    request_version: int
    person_id: UUID
    observed_at: datetime
    request_expires_at: datetime
    default_choice: ResponseChoice
    options: tuple[RequestResponseOption, ...] = field(repr=False)
