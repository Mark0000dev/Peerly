from dataclasses import dataclass
from uuid import UUID

from studymate.application.identity.sessions import (
    SessionCredential,
    SessionHasher,
    require_verified_student,
)
from studymate.application.student_notifications.subscriptions import SubscriptionUnitOfWork
from studymate.domain.student_notifications.capabilities import Capabilities, DeviceState


@dataclass(frozen=True, slots=True)
class DeliveryStatus:
    account_id: UUID
    capability: Capabilities
    device: DeviceState | None


@dataclass(frozen=True, slots=True)
class ReadOwnDelivery:
    unit: SubscriptionUnitOfWork
    hasher: SessionHasher
    capabilities: Capabilities

    async def __call__(self, credential: SessionCredential, installation: UUID) -> DeliveryStatus:
        async with self.unit.transaction() as transaction:
            identity, _ = await require_verified_student(
                transaction, await self.hasher.digest(credential)
            )
            return DeliveryStatus(
                identity.session.account_id,
                self.capabilities,
                await transaction.read(identity.session.account_id, installation),
            )
