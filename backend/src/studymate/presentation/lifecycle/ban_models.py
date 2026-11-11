"""Closed ban command and immutable receipt, excluding private reason/auth/intent data."""

from typing import Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool, model_validator

from studymate.domain.lifecycle.states import (
    MAX_LIFECYCLE_REASON_CHARACTERS,
    AccountLifecycle,
    BanRevision,
    BanTransition,
    LifecycleReason,
)


class BanHttpModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ChangeBanBody(BanHttpModel):
    banned: StrictBool
    reason: str = Field(min_length=1, max_length=MAX_LIFECYCLE_REASON_CHARACTERS, repr=False)

    @model_validator(mode="after")
    def valid_reason(self) -> Self:
        LifecycleReason(self.reason)
        return self


class BanReceiptState(BanHttpModel):
    account_id: UUID
    banned_at: AwareDatetime | None
    deleted_at: AwareDatetime | None
    source_version: int = Field(ge=0)


class BanReceiptSource(BanHttpModel):
    id: UUID
    account_id: UUID
    version: int = Field(ge=1)
    banned: bool
    changed_at: AwareDatetime


class BanChangeResponse(BanHttpModel):
    changed: bool
    account: BanReceiptState
    revision: BanReceiptSource | None
    representation: Literal["committed_command_receipt_not_current_account_read"] = (
        "committed_command_receipt_not_current_account_read"
    )


def state_response(state: AccountLifecycle) -> BanReceiptState:
    return BanReceiptState(
        account_id=state.account_id,
        banned_at=state.banned_at,
        deleted_at=state.deleted_at,
        source_version=state.source_version,
    )


def source_response(source: BanRevision) -> BanReceiptSource:
    return BanReceiptSource(
        id=source.id,
        account_id=source.account_id,
        version=source.version,
        banned=source.banned,
        changed_at=source.changed_at,
    )


def ban_response(result: BanTransition) -> BanChangeResponse:
    return BanChangeResponse(
        changed=result.changed,
        account=state_response(result.after),
        revision=source_response(result.revision) if result.revision is not None else None,
    )
