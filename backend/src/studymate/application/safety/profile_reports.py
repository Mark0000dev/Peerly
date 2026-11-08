import hmac
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID, uuid4

from studymate.application.idempotency import (
    IdempotencyConflictError,
    IntentFingerprinter,
    IntentKey,
)
from studymate.application.identity.sessions import (
    IdentityReader,
    SessionCredential,
    SessionHasher,
    StudentActionDeniedError,
    UnauthenticatedError,
    require_verified_student,
)
from studymate.domain.reports import (
    ProfileAccessContext,
    ProfileReport,
    ReportCategory,
    report_comment,
)
from studymate.domain.time import require_aware


class ReportContextUnavailableError(Exception):
    pass


class ProfileReportRateLimitedError(Exception):
    def __init__(self, retry_at: datetime) -> None:
        super().__init__("Report submission budget is exhausted")
        self.retry_at = retry_at


@dataclass(frozen=True, slots=True)
class SubmitProfileReportCommand:
    credential: SessionCredential = field(repr=False)
    context_id: UUID
    category: ReportCategory
    intent_key: IntentKey
    comment: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "comment", report_comment(self.category, self.comment))


@dataclass(frozen=True, slots=True)
class ReportIntent:
    fingerprint: bytes = field(repr=False)
    report_id: UUID


@dataclass(frozen=True, slots=True)
class ProfileReportPolicy:
    maximum_recent: int = 10
    interval: timedelta = timedelta(hours=1)

    def __post_init__(self) -> None:
        if (
            isinstance(self.maximum_recent, bool)
            or self.maximum_recent < 1
            or self.interval <= timedelta()
        ):
            raise ValueError("Reporting admission limits must be positive")


@dataclass(frozen=True, slots=True)
class ReportBudget:
    used: int
    oldest_at: datetime | None

    def __post_init__(self) -> None:
        if (
            isinstance(self.used, bool)
            or self.used < 0
            or (self.used == 0) != (self.oldest_at is None)
        ):
            raise ValueError("Report budget must reflect actual submitted history")
        if self.oldest_at is not None:
            require_aware(self.oldest_at)


class ProfileReportTransaction(IdentityReader, Protocol):
    async def report_intent(self, actor_id: UUID, key: IntentKey) -> ReportIntent | None: ...

    async def own_report(self, actor_id: UUID, report_id: UUID) -> ProfileReport | None: ...

    async def access_context(
        self, actor_id: UUID, context_id: UUID
    ) -> ProfileAccessContext | None: ...

    async def report_budget(self, actor_id: UUID, since: datetime) -> ReportBudget: ...

    async def add_report(self, report: ProfileReport) -> None: ...

    async def remember_report_intent(
        self,
        actor_id: UUID,
        key: IntentKey,
        intent: ReportIntent,
        at: datetime,
    ) -> None: ...


class ProfileReportUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[ProfileReportTransaction]: ...


@dataclass(frozen=True, slots=True)
class SubmitProfileReport:
    unit_of_work: ProfileReportUnitOfWork
    hasher: SessionHasher
    fingerprinter: IntentFingerprinter
    policy: ProfileReportPolicy = field(default_factory=ProfileReportPolicy)

    async def __call__(self, command: SubmitProfileReportCommand) -> ProfileReport:
        fingerprint = await self.fingerprinter.fingerprint(
            (
                "report.profile.v1",
                str(command.context_id),
                command.category.value,
                command.comment or "",
            )
        )
        async with self.unit_of_work.transaction() as transaction:
            actor, now = await require_verified_student(
                transaction, await self.hasher.digest(command.credential)
            )
            if not actor.activation_complete:
                raise StudentActionDeniedError
            actor_id = actor.session.account_id
            prior = await transaction.report_intent(actor_id, command.intent_key)
            if prior is not None:
                if not hmac.compare_digest(prior.fingerprint, fingerprint):
                    raise IdempotencyConflictError
                result = await transaction.own_report(actor_id, prior.report_id)
                if result is None:
                    raise RuntimeError("Saved report result is unavailable")
                return result
            context = await transaction.access_context(actor_id, command.context_id)
            if context is None or context.viewer_id != actor_id:
                raise ReportContextUnavailableError
            budget = await transaction.report_budget(actor_id, now - self.policy.interval)
            if budget.used >= self.policy.maximum_recent:
                if budget.oldest_at is None:
                    raise RuntimeError("Report quota source is unavailable")
                raise ProfileReportRateLimitedError(budget.oldest_at + self.policy.interval)
            now = await transaction.now()
            report = ProfileReport(
                uuid4(), actor_id, context, command.category, now, command.comment
            )
            await transaction.add_report(report)
            await transaction.remember_report_intent(
                actor_id, command.intent_key, ReportIntent(fingerprint, report.id), now
            )
            if not actor.session.is_active(await transaction.now()):
                raise UnauthenticatedError
            return report
