"""One ordered-account transaction for manual source, active claim, effects and receipt."""

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from studymate.application.idempotency import IntentKey
from studymate.application.operator.ports import OperatorAuditTransaction
from studymate.domain.identity import StudentEmail
from studymate.domain.operator.membership_verification import (
    ManualMembershipVerification,
    ManualVerificationTarget,
)


@dataclass(frozen=True, slots=True)
class ManualMembershipIntent:
    fingerprint: bytes = field(repr=False)
    result: ManualMembershipVerification


class ManualMembershipTransaction(OperatorAuditTransaction, Protocol):
    async def verification_target(self, account_id: UUID) -> ManualVerificationTarget | None: ...

    async def prior_manual_verification(
        self, operator_id: UUID, key: IntentKey
    ) -> ManualMembershipIntent | None: ...

    async def apply_manual_verification(
        self,
        source: ManualMembershipVerification,
        email: StudentEmail,
        key: IntentKey,
        fingerprint: bytes,
    ) -> bool:
        """Atomic unique active binding/source/event/manual provenance/receipt.

        Supersede the exact pending challenge, clear digest, cancel queued/inflight
        deliveries. NEVER consume OTP, activate profile/legal terms, create session,
        change ban/delete, retire/reassign existing binding, or send real mail.
        False means email claim/lineage conflict; caller raises and rolls back.
        Main supplies the real canonical/audit projection; no fake READ_ACCOUNT mutation.
        """
        ...


class ManualMembershipUnitOfWork(Protocol):
    def transaction(
        self, actor_secret_digest: bytes, target_account_id: UUID
    ) -> AbstractAsyncContextManager[ManualMembershipTransaction]:
        """Actual sorted actor/target account locks BEFORE session/current operator role."""
        ...
