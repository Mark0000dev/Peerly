from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from studymate.domain.requests.states import ConnectionRequest


class RequestOutcomeRecorder(Protocol):
    async def __call__(
        self, session: AsyncSession, request: ConnectionRequest, initiator_id: UUID | None
    ) -> None:
        """Required actual canonical write in caller TX; None means SYSTEM, no activity.

        Human identity is captured from the actual authenticated lock/guard, never
        a client body. Correlation origin may exist for either initiator type.
        """
        ...
