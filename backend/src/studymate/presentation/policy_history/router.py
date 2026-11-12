import base64
import binascii
from datetime import datetime
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel, ConfigDict

from studymate.application.policy_history.read import PolicyHistoryPosition, ReadPolicyHistory
from studymate.domain.registration import PolicyKind
from studymate.presentation.problems import problem
from studymate.presentation.registration_models import PolicyReferenceResponse, policy_reference

MAX_CURSOR_LENGTH = 256


class PolicyHistoryItemResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    reference: PolicyReferenceResponse
    title: str


class PolicyHistoryResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    items: tuple[PolicyHistoryItemResponse, ...]
    next_cursor: str | None


def encode_position(kind: PolicyKind, position: PolicyHistoryPosition) -> str:
    value = "|".join(
        (
            "policy-v1",
            kind.value,
            position.published_at.isoformat(),
            str(position.id),
            position.as_of.isoformat(),
        )
    )
    return base64.urlsafe_b64encode(value.encode("ascii")).decode("ascii").rstrip("=")


def decode_position(kind: PolicyKind, token: str) -> PolicyHistoryPosition:
    if not 1 <= len(token) <= MAX_CURSOR_LENGTH:
        raise ValueError("Invalid policy history cursor")
    try:
        raw = base64.b64decode(token + "=" * (-len(token) % 4), altchars=b"-_", validate=True)
        version, scope, timestamp, identity, as_of = raw.decode("ascii").split("|")
        position = PolicyHistoryPosition(
            datetime.fromisoformat(timestamp), UUID(identity), datetime.fromisoformat(as_of)
        )
        if (version, scope) != ("policy-v1", kind.value) or encode_position(
            kind, position
        ) != token:
            raise ValueError("Invalid policy history cursor")
        return position
    except (ValueError, UnicodeError, binascii.Error):
        raise ValueError("Invalid policy history cursor") from None


def policy_history_router(read: ReadPolicyHistory) -> APIRouter:
    router = APIRouter()

    @router.get("/policies/{kind}/versions", response_model=PolicyHistoryResponse)
    async def history(
        kind: PolicyKind,
        response: Response,
        limit: Annotated[int, Query(ge=1, le=50)] = 20,
        cursor: Annotated[str | None, Query(min_length=1, max_length=256)] = None,
    ) -> PolicyHistoryResponse | Response:
        try:
            before = decode_position(kind, cursor) if cursor is not None else None
            page = await read(kind, before, limit)
        except ValueError:
            return problem(HTTPStatus.UNPROCESSABLE_ENTITY, "invalid_policy_history_cursor")
        response.headers["Cache-Control"] = "public, max-age=60"
        return PolicyHistoryResponse(
            items=tuple(
                PolicyHistoryItemResponse(
                    reference=policy_reference(item.reference), title=item.title
                )
                for item in page.items
            ),
            next_cursor=encode_position(kind, page.next_position)
            if page.next_position is not None
            else None,
        )

    return router
