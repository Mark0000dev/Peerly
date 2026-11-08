import hmac
from uuid import UUID

from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.requests.ports import RequestIntent, RequestResult, RequestTransaction


async def replay(
    transaction: RequestTransaction,
    actor_id: UUID,
    operation: str,
    key: IntentKey,
    fingerprint: bytes,
) -> RequestResult | None:
    prior = await transaction.intent(actor_id, operation, key)
    if prior is None:
        return None
    if not hmac.compare_digest(prior.fingerprint, fingerprint):
        raise IdempotencyConflictError
    return prior.result


async def remember(
    transaction: RequestTransaction,
    actor_id: UUID,
    operation: str,
    key: IntentKey,
    intent: RequestIntent,
) -> None:
    await transaction.remember_intent(actor_id, operation, key, intent, await transaction.now())
