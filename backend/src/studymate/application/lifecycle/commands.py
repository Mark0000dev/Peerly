"""Immutable internal lifecycle commands; no HTTP or recovery-capability authority."""

from dataclasses import dataclass, field
from uuid import UUID

from studymate.application.idempotency import IntentKey
from studymate.application.identity.sessions import SessionCredential
from studymate.domain.lifecycle.states import LifecycleOperation, LifecycleReason


@dataclass(frozen=True, slots=True)
class ChangeAccountBanCommand:
    credential: SessionCredential = field(repr=False)
    account_id: UUID
    banned: bool
    reason: LifecycleReason = field(repr=False)
    intent_key: IntentKey = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.banned, bool):
            raise ValueError("Ban command requires an explicit boolean flag")

    @property
    def operation(self) -> LifecycleOperation:
        return LifecycleOperation.BAN if self.banned else LifecycleOperation.UNBAN

    def fingerprint_parts(self, actor_id: UUID) -> tuple[str, ...]:
        return (
            "lifecycle.v1",
            str(actor_id),
            self.operation.value,
            str(self.account_id),
            self.reason.value,
        )


@dataclass(frozen=True, slots=True)
class DeleteOwnAccountCommand:
    credential: SessionCredential = field(repr=False)
    workflow_id: UUID
    intent_key: IntentKey = field(repr=False)

    @property
    def operation(self) -> LifecycleOperation:
        return LifecycleOperation.DELETE

    def fingerprint_parts(self, actor_id: UUID, session_id: UUID) -> tuple[str, ...]:
        # IDs bind the intent; they DO NOT authorize deletion or a recovery read.
        return (
            "lifecycle.v1",
            str(actor_id),
            self.operation.value,
            str(session_id),
            str(self.workflow_id),
        )
