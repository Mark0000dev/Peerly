"""Image reports use actual peer messages; they neither block nor publish contact."""

import hmac
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from studymate.application.idempotency import (
    IdempotencyConflictError,
    IntentFingerprinter,
    IntentKey,
)
from studymate.application.identity.sessions import (
    IdentitySnapshot,
    SessionCredential,
    SessionHasher,
    StudentActionDeniedError,
    UnauthenticatedError,
    require_verified_student,
)
from studymate.application.messaging.commands import authorize_conversation
from studymate.application.safety.message_report_ports import (
    MessageReportTransaction,
    MessageReportUnitOfWork,
)
from studymate.application.safety.profile_reports import (
    ProfileReportPolicy,
    ProfileReportRateLimitedError,
    ReportContextUnavailableError,
    ReportIntent,
)
from studymate.domain.message_reports import (
    MessageImageReport,
    MessageImageReportContext,
    ReportMessageSource,
)
from studymate.domain.reports import ReportCategory, report_comment


@dataclass(frozen=True, slots=True)
class SubmitMessageImageReportCommand:
    credential: SessionCredential = field(repr=False)
    context_id: UUID
    category: ReportCategory
    intent_key: IntentKey = field(repr=False)
    comment: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "comment", report_comment(self.category, self.comment))


async def checked_source(
    tx: MessageReportTransaction,
    hasher: SessionHasher,
    credential: SessionCredential,
    conversation_id: UUID,
    message_id: UUID,
) -> tuple[IdentitySnapshot, ReportMessageSource]:
    actor, access = await authorize_conversation(tx, hasher, credential, conversation_id)
    source = await tx.message_source(actor.session.account_id, conversation_id, message_id)
    if source is None or source.image is None:
        raise ReportContextUnavailableError
    if (source.conversation_id, source.message_id, source.pair) != (
        conversation_id,
        message_id,
        access.conversation.pair,
    ):
        raise RuntimeError(
            "Message report source differs from actual conversation/message authority"
        )
    if source.author_id == actor.session.account_id:
        raise ReportContextUnavailableError
    return actor, source


async def finish(tx: MessageReportTransaction, actor: IdentitySnapshot) -> None:
    if not actor.session.is_active(await tx.now()):
        raise UnauthenticatedError


@dataclass(frozen=True, slots=True)
class IssueMessageImageReportContext:
    unit_of_work: MessageReportUnitOfWork
    hasher: SessionHasher

    async def __call__(
        self, credential: SessionCredential, conversation_id: UUID, message_id: UUID
    ) -> MessageImageReportContext:
        async with self.unit_of_work.for_message(conversation_id) as tx:
            actor, source = await checked_source(
                tx, self.hasher, credential, conversation_id, message_id
            )
            context = MessageImageReportContext(
                uuid4(), actor.session.account_id, source, await tx.now()
            )
            await tx.add_context(context)
            await finish(tx, actor)
            return context


async def retained_context(
    tx: MessageReportTransaction,
    actor_id: UUID,
    context_id: UUID,
) -> MessageImageReportContext:
    context = await tx.owned_context(actor_id, context_id)
    if context is None:
        raise ReportContextUnavailableError
    if (context.id, context.reporter_id) != (context_id, actor_id):
        raise RuntimeError("Message report context differs from its actual retained owner")
    return context


@dataclass(frozen=True, slots=True)
class SubmitMessageImageReport:
    unit_of_work: MessageReportUnitOfWork
    hasher: SessionHasher
    fingerprinter: IntentFingerprinter
    policy: ProfileReportPolicy = field(default_factory=ProfileReportPolicy)

    async def __call__(self, command: SubmitMessageImageReportCommand) -> MessageImageReport:
        digest = await self.hasher.digest(command.credential)
        fingerprint = await self.fingerprinter.fingerprint(
            (
                "report.message-image.v1",
                str(command.context_id),
                command.category.value,
                command.comment or "",
            )
        )
        async with self.unit_of_work.for_context(command.context_id) as tx:
            initial, _ = await require_verified_student(tx, digest)
            if not initial.activation_complete:
                raise StudentActionDeniedError
            actor_id = initial.session.account_id
            prior = await tx.report_intent(actor_id, command.intent_key)
            if prior is not None and not hmac.compare_digest(prior.fingerprint, fingerprint):
                raise IdempotencyConflictError
            context = await retained_context(tx, actor_id, command.context_id)
            actor, current = await checked_source(
                tx,
                self.hasher,
                command.credential,
                context.source.conversation_id,
                context.source.message_id,
            )
            if (actor.session.id, actor.session.account_id) != (initial.session.id, actor_id):
                raise UnauthenticatedError
            if current != context.source:
                raise ReportContextUnavailableError
            if prior is not None:
                result = await tx.own_message_report(actor_id, prior.report_id)
                if result is None or (result.id, result.reporter_id, result.context) != (
                    prior.report_id,
                    actor_id,
                    context,
                ):
                    raise RuntimeError(
                        "Retained message report intent lost its exact original result"
                    )
            else:
                now = await tx.now()
                budget = await tx.report_budget(actor_id, now - self.policy.interval)
                if budget.used >= self.policy.maximum_recent:
                    if budget.oldest_at is None:
                        raise RuntimeError("Unified report quota lost its actual submitted source")
                    raise ProfileReportRateLimitedError(budget.oldest_at + self.policy.interval)
                result = MessageImageReport(
                    uuid4(), actor_id, context, command.category, await tx.now(), command.comment
                )
                await tx.add_message_report(result)
                await tx.remember_report_intent(
                    actor_id,
                    command.intent_key,
                    ReportIntent(fingerprint, result.id),
                    result.submitted_at,
                )
            await finish(tx, actor)
            return result
