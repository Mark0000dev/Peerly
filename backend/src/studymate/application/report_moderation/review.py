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
from studymate.application.report_moderation.ports import ReportModerationUnitOfWork
from studymate.domain.report_moderation.reviews import (
    MAX_REVIEW_VERSION,
    ReportReviewAction,
    ReportReviewReason,
    ReportReviewRevision,
)


class ReportReviewUnavailableError(Exception):
    pass


class ReportReviewVersionConflictError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class ReviewReportCommand:
    credential: SessionCredential = field(repr=False)
    report_id: UUID
    expected_version: int
    action: ReportReviewAction
    reason: ReportReviewReason = field(repr=False)
    intent_key: IntentKey

    def __post_init__(self) -> None:
        if (
            isinstance(self.expected_version, bool)
            or not 0 <= self.expected_version < MAX_REVIEW_VERSION
        ):
            raise ValueError("Report review requires a bounded expected source version")

    def fingerprint_parts(self) -> tuple[str, ...]:
        return (
            "operator.report-review.v1",
            str(self.report_id),
            str(self.expected_version),
            self.action.value,
            self.reason.value,
        )


@dataclass(frozen=True, slots=True)
class ReviewReport:
    unit_of_work: ReportModerationUnitOfWork
    hasher: SessionHasher
    fingerprinter: IntentFingerprinter

    async def __call__(self, command: ReviewReportCommand) -> ReportReviewRevision:
        digest = await self.hasher.digest(command.credential)
        async with self.unit_of_work.transaction(digest, command.report_id) as transaction:
            principal = await require_operator(transaction, command.credential, self.hasher)
            report = await transaction.lock_report(command.report_id)
            if report is None:
                raise ReportReviewUnavailableError
            if report.id != command.report_id:
                raise RuntimeError("Report review source differs from requested report")
            fingerprint = await self.fingerprinter.fingerprint(command.fingerprint_parts())
            prior = await transaction.prior_review(principal.access.account_id, command.intent_key)
            if prior is not None:
                if not hmac.compare_digest(prior.fingerprint, fingerprint):
                    raise IdempotencyConflictError
                if (
                    prior.result.report_id != command.report_id
                    or prior.result.operator.account_id != principal.access.account_id
                ):
                    raise RuntimeError("Report review receipt differs from its actual actor/report")
                await finish_operator(transaction, principal)
                return prior.result
            previous = await transaction.latest_review(command.report_id)
            version = previous.version if previous is not None else 0
            if previous is not None and previous.report_id != command.report_id:
                raise RuntimeError("Report review head differs from requested report")
            if version != command.expected_version:
                raise ReportReviewVersionConflictError
            source = ReportReviewRevision(
                uuid4(),
                command.report_id,
                version + 1,
                version if version else None,
                command.action,
                command.reason.value,
                principal.access,
                principal.identity.session.id,
                await transaction.now(),
                uuid4(),
            )
            persisted = await transaction.append_review(source, command.intent_key, fingerprint)
            if replace(persisted, origin=source.origin) != source:
                raise RuntimeError("Report review persisted proof differs from its actual source")
            await finish_operator(transaction, principal)
            return persisted
