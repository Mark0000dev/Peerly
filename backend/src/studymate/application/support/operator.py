import hmac
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID, uuid4

from studymate.application.idempotency import (
    IdempotencyConflictError,
    IntentFingerprinter,
    IntentKey,
)
from studymate.application.identity.sessions import SessionCredential, SessionHasher
from studymate.application.operator.authority import finish_operator, require_operator
from studymate.application.operator.ports import OperatorAuditTransaction
from studymate.application.support.cases import SupportIntent
from studymate.domain.operator.access import OperatorAccess
from studymate.domain.operator.audit import (
    OperatorAction,
    OperatorAudit,
    OperatorAuditOutcome,
    OperatorResourceKind,
    OperatorResourceRef,
)
from studymate.domain.support.cases import SupportContent, SupportReceipt, SupportStatus


class SupportVersionConflictError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class OperatorSupportCase:
    receipt: SupportReceipt
    actor_id: UUID | None
    content: SupportContent = field(repr=False)


@dataclass(frozen=True, slots=True)
class ChangeSupportStatusCommand:
    credential: SessionCredential = field(repr=False)
    case_id: UUID
    status: SupportStatus
    expected_version: int
    key: IntentKey

    def __post_init__(self) -> None:
        if isinstance(self.expected_version, bool) or self.expected_version < 1:
            raise ValueError("Support status requires a positive expected revision")


class OperatorSupportTransaction(OperatorAuditTransaction, Protocol):
    async def case(self, case_id: UUID) -> OperatorSupportCase | None: ...

    async def status_intent(self, operator_id: UUID, key: IntentKey) -> SupportIntent | None: ...

    async def save_status(self, access: OperatorAccess, receipt: SupportReceipt) -> None: ...

    async def remember_status(
        self, operator_id: UUID, key: IntentKey, intent: SupportIntent, at: datetime
    ) -> None: ...


class OperatorSupportUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[OperatorSupportTransaction]: ...


async def _audit(
    transaction: OperatorSupportTransaction, access: OperatorAccess, case_id: UUID, exists: bool
) -> None:
    ref = OperatorResourceRef(OperatorResourceKind.SUPPORT_CASE, case_id)
    await transaction.save_operator_audit(
        OperatorAudit(
            uuid4(),
            access,
            OperatorAction.READ_SUPPORT_CASE,
            ref,
            (ref,) if exists else (),
            await transaction.now(),
            OperatorAuditOutcome.READ if exists else OperatorAuditOutcome.NOT_FOUND,
        )
    )


@dataclass(frozen=True, slots=True)
class ReadOperatorSupportCase:
    unit_of_work: OperatorSupportUnitOfWork
    hasher: SessionHasher

    async def __call__(
        self, credential: SessionCredential, case_id: UUID
    ) -> OperatorSupportCase | None:
        async with self.unit_of_work.transaction() as transaction:
            principal = await require_operator(transaction, credential, self.hasher)
            result = await transaction.case(case_id)
            await _audit(transaction, principal.access, case_id, result is not None)
            await finish_operator(transaction, principal)
            return result


@dataclass(frozen=True, slots=True)
class ChangeOperatorSupportStatus:
    unit_of_work: OperatorSupportUnitOfWork
    hasher: SessionHasher
    fingerprinter: IntentFingerprinter

    async def __call__(self, command: ChangeSupportStatusCommand) -> SupportReceipt | None:
        async with self.unit_of_work.transaction() as transaction:
            principal = await require_operator(transaction, command.credential, self.hasher)
            owner = principal.access.account_id
            fingerprint = await self.fingerprinter.fingerprint(
                (
                    "support.status.v1",
                    str(command.case_id),
                    str(command.expected_version),
                    command.status.value,
                )
            )
            prior = await transaction.status_intent(owner, command.key)
            if prior is not None:
                if not hmac.compare_digest(prior.fingerprint, fingerprint):
                    raise IdempotencyConflictError
                result = prior.receipt
            else:
                case = await transaction.case(command.case_id)
                if case is None:
                    await _audit(transaction, principal.access, command.case_id, False)
                    await finish_operator(transaction, principal)
                    return None
                current = case.receipt
                if current.version != command.expected_version:
                    raise SupportVersionConflictError
                result = current
                at = await transaction.now()
                if current.status != command.status:
                    result = SupportReceipt(
                        current.case_id,
                        command.status,
                        current.version + 1,
                        current.received_at,
                        at,
                    )
                    await transaction.save_status(principal.access, result)
                await transaction.remember_status(
                    owner, command.key, SupportIntent(fingerprint, result), at
                )
            await _audit(transaction, principal.access, command.case_id, True)
            await finish_operator(transaction, principal)
            return result
