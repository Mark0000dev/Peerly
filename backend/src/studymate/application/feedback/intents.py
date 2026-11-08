import hmac
from dataclasses import dataclass
from uuid import UUID

from studymate.application.feedback.ports import (
    FeedbackIntent,
    FeedbackOperation,
    FeedbackTransaction,
)
from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.sessions import IdentitySnapshot, UnauthenticatedError


@dataclass(frozen=True, slots=True)
class FeedbackIntentScope:
    actor_id: UUID
    operation: FeedbackOperation
    key: IntentKey
    fingerprint: bytes


async def prior_intent(
    transaction: FeedbackTransaction, scope: FeedbackIntentScope
) -> FeedbackIntent | None:
    prior = await transaction.feedback_intent(scope.actor_id, scope.operation, scope.key)
    if prior is not None and not hmac.compare_digest(prior.fingerprint, scope.fingerprint):
        raise IdempotencyConflictError
    return prior


async def finish_feedback(transaction: FeedbackTransaction, actor: IdentitySnapshot) -> None:
    if not actor.session.is_active(await transaction.now()):
        raise UnauthenticatedError
