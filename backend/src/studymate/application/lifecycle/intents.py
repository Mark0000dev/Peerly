"""Actor/operation/key-bound retained immutable lifecycle results, not a workflow engine."""

import hmac
from dataclasses import dataclass, field
from uuid import UUID

from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.sessions import IdentitySnapshot
from studymate.application.lifecycle.commands import (
    ChangeAccountBanCommand,
    DeleteOwnAccountCommand,
)
from studymate.domain.lifecycle.states import BanTransition, DeletionTransition, LifecycleOperation

LIFECYCLE_FINGERPRINT_BYTES = 32

type LifecycleResult = BanTransition | DeletionTransition


@dataclass(frozen=True, slots=True)
class LifecycleIntent:
    actor_id: UUID
    operation: LifecycleOperation
    key: IntentKey = field(repr=False)
    fingerprint: bytes = field(repr=False)
    result: LifecycleResult = field(repr=False)

    def __post_init__(self) -> None:
        if len(self.fingerprint) != LIFECYCLE_FINGERPRINT_BYTES:
            raise ValueError("Lifecycle intent requires its actual payload HMAC")
        if isinstance(self.result, DeletionTransition):
            if (
                self.operation != LifecycleOperation.DELETE
                or self.result.revision.account_id != self.actor_id
            ):
                raise ValueError(
                    "Deletion intent differs from its actual self-owned immutable result"
                )
        else:
            expected = (
                LifecycleOperation.BAN
                if self.result.after.banned_at is not None
                else LifecycleOperation.UNBAN
            )
            source = self.result.revision
            if self.operation != expected or (
                source is not None and source.operator_access.account_id != self.actor_id
            ):
                raise ValueError("Ban intent differs from its actual operator/flag result")


def _resolve_owned_intent(
    stored: LifecycleIntent | None,
    *,
    actor_id: UUID,
    operation: LifecycleOperation,
    key: IntentKey,
    fingerprint: bytes,
) -> LifecycleResult | None:
    if len(fingerprint) != LIFECYCLE_FINGERPRINT_BYTES:
        raise ValueError("Lifecycle replay requires its actual payload HMAC")
    if stored is None:
        return None
    if (stored.actor_id, stored.operation, stored.key) != (actor_id, operation, key):
        raise RuntimeError("Lifecycle intent source belongs to another actor, operation or key")
    if not hmac.compare_digest(stored.fingerprint, fingerprint):
        raise IdempotencyConflictError
    return stored.result


def resolve_ban_intent(
    stored: LifecycleIntent | None,
    command: ChangeAccountBanCommand,
    actor_id: UUID,
    fingerprint: bytes,
) -> BanTransition | None:
    result = _resolve_owned_intent(
        stored,
        actor_id=actor_id,
        operation=command.operation,
        key=command.intent_key,
        fingerprint=fingerprint,
    )
    if result is None:
        return None
    if not isinstance(result, BanTransition) or result.after.account_id != command.account_id:
        raise RuntimeError("Ban replay differs from its exact retained target/result source")
    return result


def resolve_deletion_intent(
    stored: LifecycleIntent | None,
    command: DeleteOwnAccountCommand,
    identity: IdentitySnapshot,
    fingerprint: bytes,
) -> DeletionTransition | None:
    """Resolve an already owned committed result; this grants NO new mutation authority.

    Actual credential/workflow recovery proof remains the main transaction's prerequisite.
    A revoked original session can identify its committed receipt, never a new deletion.
    """
    result = _resolve_owned_intent(
        stored,
        actor_id=identity.session.account_id,
        operation=command.operation,
        key=command.intent_key,
        fingerprint=fingerprint,
    )
    if result is None:
        return None
    if not isinstance(result, DeletionTransition) or (
        result.revision.actor_session_id,
        result.revision.workflow_id,
    ) != (identity.session.id, command.workflow_id):
        raise RuntimeError("Deletion replay differs from its actual original session/workflow")
    return result
