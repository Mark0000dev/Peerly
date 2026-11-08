"""Closed deletion command and actual committed receipt, never an erasure/restore claim."""

from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from studymate.domain.lifecycle.states import DeletionTransition


class DeleteAccountBody(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    workflow_id: UUID


class DeletionReceiptResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    workflow_id: UUID
    deleted_at: AwareDatetime
    source_version: int = Field(ge=1)


def deletion_response(result: DeletionTransition) -> DeletionReceiptResponse:
    source = result.revision
    return DeletionReceiptResponse(
        workflow_id=source.workflow_id, deleted_at=source.deleted_at, source_version=source.version
    )
