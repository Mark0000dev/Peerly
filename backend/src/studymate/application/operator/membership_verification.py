"""Privileged manual membership approval; submitted email is not OTP consumption."""

import hmac
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from studymate.application.idempotency import (
    IdempotencyConflictError,
    IntentFingerprinter,
    IntentKey,
)
from studymate.application.identity.sessions import SessionCredential, SessionHasher
from studymate.application.operator.authority import finish_operator, require_operator
from studymate.application.operator.membership_verification_ports import ManualMembershipUnitOfWork
from studymate.domain.identity import StudentEmail
from studymate.domain.operator.audit import (
    OperatorAction,
    OperatorAudit,
    OperatorAuditOutcome,
    OperatorResourceKind,
    OperatorResourceRef,
)
from studymate.domain.operator.membership_verification import (
    ManualMembershipVerification,
    ManualVerificationTarget,
)


class ManualMembershipUnavailableError(Exception):
    pass


class ManualMembershipPreconditionError(Exception):
    pass


class ManualMembershipClaimConflictError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class ManuallyVerifyMembershipCommand:
    credential: SessionCredential = field(repr=False)
    account_id: UUID
    expected_google_identity_id: UUID
    expected_challenge_id: UUID
    expected_email: StudentEmail = field(repr=False)
    intent_key: IntentKey

    def fingerprint_parts(self) -> tuple[str, ...]:
        return (
            "operator.manual-membership.v1",
            str(self.account_id),
            str(self.expected_google_identity_id),
            str(self.expected_challenge_id),
            self.expected_email.value,
        )


@dataclass(frozen=True, slots=True)
class ReadManualMembershipContext:
    unit_of_work: ManualMembershipUnitOfWork
    hasher: SessionHasher

    async def __call__(
        self, credential: SessionCredential, account_id: UUID
    ) -> ManualVerificationTarget | None:
        async with self.unit_of_work.transaction(
            await self.hasher.digest(credential), account_id
        ) as transaction:
            principal = await require_operator(transaction, credential, self.hasher)
            target = await transaction.verification_target(account_id)
            if target is not None and target.account_id != account_id:
                raise RuntimeError(
                    "Manual context source differs from the actual requested account"
                )
            ref = OperatorResourceRef(OperatorResourceKind.ACCOUNT, account_id)
            await transaction.save_operator_audit(
                OperatorAudit(
                    uuid4(),
                    principal.access,
                    OperatorAction.READ_ACCOUNT,
                    ref,
                    (ref,) if target is not None else (),
                    await transaction.now(),
                    OperatorAuditOutcome.READ
                    if target is not None
                    else OperatorAuditOutcome.NOT_FOUND,
                )
            )
            await finish_operator(transaction, principal)
            return target


@dataclass(frozen=True, slots=True)
class ManuallyVerifyMembership:
    unit_of_work: ManualMembershipUnitOfWork
    hasher: SessionHasher
    fingerprinter: IntentFingerprinter

    async def __call__(
        self, command: ManuallyVerifyMembershipCommand
    ) -> ManualMembershipVerification:
        digest = await self.hasher.digest(command.credential)
        async with self.unit_of_work.transaction(digest, command.account_id) as transaction:
            principal = await require_operator(transaction, command.credential, self.hasher)
            target = await transaction.verification_target(command.account_id)
            if target is None or target.deleted or target.banned or target.lineage_banned:
                raise ManualMembershipUnavailableError
            if target.account_id != command.account_id:
                raise RuntimeError("Manual verification source differs from its ordered target")
            if target.google_identity_id != command.expected_google_identity_id:
                raise ManualMembershipPreconditionError
            fingerprint = await self.fingerprinter.fingerprint(command.fingerprint_parts())
            prior = await transaction.prior_manual_verification(
                principal.access.account_id, command.intent_key
            )
            if prior is not None:
                if not hmac.compare_digest(prior.fingerprint, fingerprint):
                    raise IdempotencyConflictError
                result = prior.result
                if (
                    result.account_id,
                    result.operator.account_id,
                    result.challenge_id,
                    result.google_identity_id,
                    result.email,
                ) != (
                    command.account_id,
                    principal.access.account_id,
                    command.expected_challenge_id,
                    command.expected_google_identity_id,
                    command.expected_email,
                ):
                    raise RuntimeError(
                        "Manual verification receipt lost its original actor/target/source"
                    )
            else:
                latest = target.latest
                if target.block is not None or latest is None:
                    raise ManualMembershipUnavailableError
                if (
                    latest.id != command.expected_challenge_id
                    or latest.email != command.expected_email
                ):
                    raise ManualMembershipPreconditionError
                result = ManualMembershipVerification(
                    uuid4(),
                    command.account_id,
                    command.expected_google_identity_id,
                    latest.id,
                    principal.access,
                    principal.identity.session.id,
                    uuid4(),
                    latest.email,
                    await transaction.now(),
                )
                if not await transaction.apply_manual_verification(
                    result, latest.email, command.intent_key, fingerprint
                ):
                    raise ManualMembershipClaimConflictError
            await finish_operator(transaction, principal)
            return result
