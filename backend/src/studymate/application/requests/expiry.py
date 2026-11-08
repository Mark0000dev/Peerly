from dataclasses import dataclass

from studymate.application.requests.ports import RequestExpiryUnitOfWork
from studymate.domain.requests.states import ConnectionRequest

MAX_EXPIRY_BATCH = 100


@dataclass(frozen=True, slots=True)
class ExpireRequests:
    """Trusted bounded internal maintenance, never a student/operator permission grant."""

    unit_of_work: RequestExpiryUnitOfWork

    async def __call__(self, limit: int = MAX_EXPIRY_BATCH) -> tuple[ConnectionRequest, ...]:
        if isinstance(limit, bool) or not 1 <= limit <= MAX_EXPIRY_BATCH:
            raise ValueError("Expiry batch must be within1..100")
        async with self.unit_of_work.transaction() as transaction:
            at = await transaction.now()
            due = await transaction.due_requests(at, limit)
            if len(due) > limit:
                raise RuntimeError("Expiry adapter exceeded requested batch")
            changed = []
            for request in due:
                effective = request.effective(at)
                if effective != request:
                    await transaction.save_request(effective)
                    changed.append(effective)
            return tuple(changed)
