from uuid import UUID

from pydantic import AwareDatetime, Field

from studymate.application.operator.block_history import OperatorBlockHistoryPage
from studymate.domain.operator.block_history import OPERATOR_BLOCK_HISTORY_PAGE_SIZE
from studymate.domain.relationships import BlockRevision
from studymate.presentation.operator.models import ClosedModel


class OperatorBlockHistoryQuery(ClosedModel):
    cursor: str | None = Field(default=None, min_length=1, max_length=1024, repr=False)


class OperatorBlockRevisionResponse(ClosedModel):
    relationship_id: UUID
    low_id: UUID
    high_id: UUID
    blocker_id: UUID
    target_id: UUID
    version: int
    blocked: bool
    changed_at: AwareDatetime


class OperatorBlockHistoryAnchorsResponse(ClosedModel):
    low_version: int = Field(ge=0)
    high_version: int = Field(ge=0)


class OperatorBlockHistoryResponse(ClosedModel):
    account_id: UUID
    relationship_id: UUID
    low_id: UUID
    high_id: UUID
    current_heads: tuple[OperatorBlockRevisionResponse, ...] = Field(max_length=2)
    revisions: tuple[OperatorBlockRevisionResponse, ...] = Field(
        max_length=OPERATOR_BLOCK_HISTORY_PAGE_SIZE
    )
    anchors: OperatorBlockHistoryAnchorsResponse
    next_cursor: str | None


def block_revision_response(value: BlockRevision) -> OperatorBlockRevisionResponse:
    return OperatorBlockRevisionResponse(
        relationship_id=value.relationship_id,
        low_id=value.pair.low,
        high_id=value.pair.high,
        blocker_id=value.blocker_id,
        target_id=value.target_id,
        version=value.version,
        blocked=value.blocked,
        changed_at=value.changed_at,
    )


def block_history_response(value: OperatorBlockHistoryPage) -> OperatorBlockHistoryResponse:
    return OperatorBlockHistoryResponse(
        account_id=value.account_id,
        relationship_id=value.relationship_id,
        low_id=value.pair.low,
        high_id=value.pair.high,
        current_heads=tuple(block_revision_response(row) for row in value.current_heads),
        revisions=tuple(block_revision_response(row) for row in value.revisions),
        anchors=OperatorBlockHistoryAnchorsResponse(
            low_version=value.anchors.low_version, high_version=value.anchors.high_version
        ),
        next_cursor=value.next_cursor,
    )
