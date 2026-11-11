from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from studymate.application.operator.conversation_index import OperatorConversationsPage
from studymate.domain.operator.conversation_index import OPERATOR_CONVERSATION_PAGE_SIZE


class OperatorConversationsQuery(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    cursor: str | None = Field(default=None, min_length=1, max_length=1024, repr=False)


class OperatorConversationSummaryResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: UUID
    relationship_id: UUID
    low_id: UUID
    high_id: UUID
    request_id: UUID
    accepted_request_version: int = Field(ge=2)


class OperatorConversationsResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    account_id: UUID
    conversations: tuple[OperatorConversationSummaryResponse, ...] = Field(
        max_length=OPERATOR_CONVERSATION_PAGE_SIZE
    )
    next_cursor: str | None


def conversations_response(page: OperatorConversationsPage) -> OperatorConversationsResponse:
    return OperatorConversationsResponse(
        account_id=page.account_id,
        conversations=tuple(
            OperatorConversationSummaryResponse(
                id=row.id,
                relationship_id=row.relationship_id,
                low_id=row.low_id,
                high_id=row.high_id,
                request_id=row.request_id,
                accepted_request_version=row.accepted_request_version,
            )
            for row in page.conversations
        ),
        next_cursor=page.next_cursor,
    )
