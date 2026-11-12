"""Human-only replacement requirement/approval, never automated AI moderation."""

import hmac
from dataclasses import dataclass, field, replace
from uuid import UUID, uuid4

from studymate.application.idempotency import (
    IdempotencyConflictError,
    IntentFingerprinter,
    IntentKey,
)
from studymate.application.identity.sessions import SessionCredential, SessionHasher
from studymate.application.operator.authority import finish_operator, require_operator
from studymate.application.operator.photo_review_ports import (
    PhotoReviewTarget,
    PhotoReviewUnitOfWork,
)
from studymate.domain.operator.audit import (
    OperatorAction,
    OperatorAudit,
    OperatorAuditOutcome,
    OperatorResourceKind,
    OperatorResourceRef,
)
from studymate.domain.operator.photo_review import (
    MAX_PHOTO_REVIEW_REASON,
    PhotoReviewAction,
    PhotoReviewRevision,
)
from studymate.domain.text import plain_text


class PhotoReviewUnavailableError(Exception):
    pass


class PhotoReviewVersionConflictError(Exception):
    pass


class PhotoReviewApprovalConflictError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class ReviewPhotoCommand:
    credential: SessionCredential = field(repr=False)
    account_id: UUID
    expected_version: int
    expected_photo_version: int
    expected_upload_id: UUID
    action: PhotoReviewAction
    reason: str = field(repr=False)
    intent_key: IntentKey

    def __post_init__(self) -> None:
        if (
            isinstance(self.expected_version, bool)
            or self.expected_version < 0
            or isinstance(self.expected_photo_version, bool)
            or self.expected_photo_version < 1
        ):
            raise ValueError(
                "Photo review requires exact nonnegative review and positive photo revisions"
            )
        object.__setattr__(
            self,
            "reason",
            plain_text(self.reason, minimum=1, maximum=MAX_PHOTO_REVIEW_REASON, multiline=True),
        )

    def fingerprint_parts(self) -> tuple[str, ...]:
        return (
            "operator.photo-review.v1",
            str(self.account_id),
            str(self.expected_version),
            str(self.expected_photo_version),
            str(self.expected_upload_id),
            self.action.value,
            self.reason,
        )


@dataclass(frozen=True, slots=True)
class ReviewPhoto:
    unit_of_work: PhotoReviewUnitOfWork
    hasher: SessionHasher
    fingerprinter: IntentFingerprinter

    async def __call__(self, command: ReviewPhotoCommand) -> PhotoReviewRevision:
        digest = await self.hasher.digest(command.credential)
        async with self.unit_of_work.transaction(digest, command.account_id) as transaction:
            principal = await require_operator(transaction, command.credential, self.hasher)
            fingerprint = await self.fingerprinter.fingerprint(command.fingerprint_parts())
            prior = await transaction.prior_photo_review(
                principal.access.account_id, command.intent_key
            )
            if prior is not None:
                if not hmac.compare_digest(prior.fingerprint, fingerprint):
                    raise IdempotencyConflictError
                if (
                    prior.result.account_id != command.account_id
                    or prior.result.operator_id != principal.access.account_id
                ):
                    raise RuntimeError("Photo review intent lost its actual actor/target")
                await finish_operator(transaction, principal)
                return prior.result
            target = await transaction.photo_review_target(command.account_id)
            if target is None or target.current_photo is None:
                raise PhotoReviewUnavailableError
            if (
                target.account_id != command.account_id
                or target.current_photo.account_id != command.account_id
            ):
                raise RuntimeError("Photo review source belongs to another account")
            previous = target.current_review
            version = previous.version if previous is not None else 0
            if (
                version != command.expected_version
                or target.current_photo.version != command.expected_photo_version
                or target.current_photo.upload_id != command.expected_upload_id
            ):
                raise PhotoReviewVersionConflictError
            if command.action == PhotoReviewAction.APPROVE_REPLACEMENT and (
                previous is None
                or not previous.replacement_required
                or target.current_photo.version <= previous.photo.version
                or target.current_photo.upload_id == previous.photo.upload_id
            ):
                raise PhotoReviewApprovalConflictError
            result = PhotoReviewRevision(
                uuid4(),
                command.account_id,
                version + 1,
                previous.id if previous is not None else None,
                command.action,
                target.current_photo,
                principal.access.account_id,
                principal.identity.session.id,
                principal.access.version,
                await transaction.now(),
                command.reason,
            )
            if previous is not None:
                previous.validate_successor(result)
            stored = await transaction.save_photo_review(result, command.intent_key, fingerprint)
            if replace(stored, origin=result.origin) != result:
                raise RuntimeError("Photo review persistence changed its original source proof")
            await finish_operator(transaction, principal)
            return stored


@dataclass(frozen=True, slots=True)
class ReadPhotoReviewContext:
    unit_of_work: PhotoReviewUnitOfWork
    hasher: SessionHasher

    async def __call__(
        self, credential: SessionCredential, account_id: UUID
    ) -> PhotoReviewTarget | None:
        digest = await self.hasher.digest(credential)
        async with self.unit_of_work.transaction(digest, account_id) as transaction:
            principal = await require_operator(transaction, credential, self.hasher)
            target = await transaction.photo_review_target(account_id)
            if target is not None and target.account_id != account_id:
                raise RuntimeError("Photo review context belongs to another account")
            reference = OperatorResourceRef(OperatorResourceKind.ACCOUNT, account_id)
            await transaction.save_operator_audit(
                OperatorAudit(
                    uuid4(),
                    principal.access,
                    OperatorAction.READ_ACCOUNT,
                    reference,
                    (reference,) if target is not None else (),
                    await transaction.now(),
                    OperatorAuditOutcome.READ
                    if target is not None
                    else OperatorAuditOutcome.NOT_FOUND,
                )
            )
            await finish_operator(transaction, principal)
            return target
