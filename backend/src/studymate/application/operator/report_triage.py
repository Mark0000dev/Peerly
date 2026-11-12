"""Privileged optional report prioritisation through the existing bounded AI queue."""

import hmac
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from studymate.application.ai.ports import Admission
from studymate.application.idempotency import IntentFingerprinter, IntentKey
from studymate.application.identity.sessions import SessionCredential, SessionHasher
from studymate.application.operator.authority import finish_operator, require_operator
from studymate.application.operator.report_triage_ports import (
    OperatorReportTriageTransaction,
    OperatorReportTriageUnitOfWork,
    ReportTriageSourceCodec,
    ReportTriageSourceUnavailableError,
    StoredReportTriage,
)
from studymate.domain.ai.tasks import TriageReport
from studymate.domain.operator.access import OperatorAccess
from studymate.domain.operator.audit import (
    OperatorAction,
    OperatorAudit,
    OperatorAuditOutcome,
    OperatorResourceKind,
    OperatorResourceRef,
)
from studymate.domain.operator.report_triage import (
    TRIAGE_SOURCE_TOKEN_LIFETIME,
    OperatorReportTriageObservation,
    ReportTriageSourceClaims,
    ReportTriageSourcePreview,
    ReportTriageSubmission,
    observe_report_triage,
)

MAX_TRIAGE_SOURCE_TOKEN_LENGTH = 1024


@dataclass(frozen=True, slots=True)
class ReportTriageContextView:
    preview: ReportTriageSourcePreview
    source_token: str | None = field(repr=False)


@dataclass(frozen=True, slots=True)
class ReportTriageView:
    observation: OperatorReportTriageObservation = field(repr=False)
    submission: ReportTriageSubmission


@dataclass(frozen=True, slots=True)
class EnqueueReportTriageCommand:
    credential: SessionCredential = field(repr=False)
    report_id: UUID
    source_token: str = field(repr=False)
    intent_key: IntentKey

    def __post_init__(self) -> None:
        if not 1 <= len(self.source_token) <= MAX_TRIAGE_SOURCE_TOKEN_LENGTH:
            raise ValueError("Triage requires the bounded server-issued source token")


async def audit_triage_read(
    transaction: OperatorReportTriageTransaction,
    access: OperatorAccess,
    report_id: UUID,
    found: bool,
) -> None:
    reference = OperatorResourceRef(OperatorResourceKind.REPORT, report_id)
    await transaction.save_operator_audit(
        OperatorAudit(
            uuid4(),
            access,
            OperatorAction.READ_REPORT,
            reference,
            (reference,) if found else (),
            await transaction.now(),
            OperatorAuditOutcome.READ if found else OperatorAuditOutcome.NOT_FOUND,
        )
    )


async def triage_view(
    transaction: OperatorReportTriageTransaction, stored: StoredReportTriage, report_id: UUID
) -> ReportTriageView:
    if (
        stored.snapshot.report.id != report_id
        or stored.submission.report_id != report_id
        or stored.submission.job_id != stored.job.id
        or stored.job.actor_id != stored.submission.operator.account_id
        or not isinstance(stored.job.task, TriageReport)
        or stored.job.task != stored.snapshot.task
        or stored.submission.source_version != stored.snapshot.version
        or stored.submission.operator != stored.snapshot.operator
        or stored.submission.actor_session_id != stored.snapshot.actor_session_id
    ):
        raise RuntimeError("Triage job differs from its actual report/snapshot/actor proof")
    failure = await transaction.triage_source_failure(stored)
    return ReportTriageView(
        observe_report_triage(report_id, stored.job, source_current=failure is None),
        stored.submission,
    )


@dataclass(frozen=True, slots=True)
class ReadReportTriageContext:
    unit_of_work: OperatorReportTriageUnitOfWork
    hasher: SessionHasher
    source_codec: ReportTriageSourceCodec

    async def __call__(
        self, credential: SessionCredential, report_id: UUID
    ) -> ReportTriageContextView | None:
        digest = await self.hasher.digest(credential)
        async with self.unit_of_work.transaction(digest, report_id) as transaction:
            principal = await require_operator(transaction, credential, self.hasher)
            preview = await transaction.lock_triage_context(report_id)
            result = None
            if preview is not None:
                token = None
                context = preview.context
                if preview.report.id != report_id:
                    raise RuntimeError("Triage source preview differs from requested report")
                if context is not None:
                    at = await transaction.now()
                    token = self.source_codec.encode_source(
                        ReportTriageSourceClaims(
                            report_id,
                            principal.access.account_id,
                            principal.identity.session.id,
                            principal.access.version,
                            context.review_version,
                            context.evidence_digest,
                            at,
                            at + TRIAGE_SOURCE_TOKEN_LIFETIME,
                        )
                    )
                result = ReportTriageContextView(preview, token)
            await audit_triage_read(transaction, principal.access, report_id, preview is not None)
            await finish_operator(transaction, principal)
            return result


@dataclass(frozen=True, slots=True)
class EnqueueReportTriage:
    unit_of_work: OperatorReportTriageUnitOfWork
    hasher: SessionHasher
    fingerprinter: IntentFingerprinter
    source_codec: ReportTriageSourceCodec

    async def __call__(self, command: EnqueueReportTriageCommand) -> ReportTriageView:
        actor_digest = await self.hasher.digest(command.credential)
        digest = await self.fingerprinter.fingerprint(
            ("operator.report-triage.v1", str(command.report_id), command.source_token)
        )
        async with self.unit_of_work.transaction(actor_digest, command.report_id) as transaction:
            principal = await require_operator(transaction, command.credential, self.hasher)
            prior = await transaction.replay_triage(
                principal.access.account_id, command.intent_key, digest
            )
            if prior is not None:
                result = await triage_view(transaction, prior, command.report_id)
                await finish_operator(transaction, principal)
                return result
            at = await transaction.now()
            claims = self.source_codec.decode_source(
                command.source_token,
                principal.access,
                principal.identity.session.id,
                command.report_id,
                at,
            )
            preview = await transaction.lock_triage_context(command.report_id)
            context = preview.context if preview is not None else None
            if (
                context is None
                or context.report.id != command.report_id
                or context.review_version != claims.review_version
                or not hmac.compare_digest(context.evidence_digest, claims.evidence_digest)
            ):
                raise ReportTriageSourceUnavailableError
            snapshot = await transaction.materialize_triage_source(
                context, principal.access, principal.identity.session.id, at
            )
            if (
                snapshot.report != context.report
                or snapshot.operator != principal.access
                or snapshot.actor_session_id != principal.identity.session.id
                or snapshot.evidence != context.evidence
                or snapshot.review_version != context.review_version
            ):
                raise RuntimeError("Triage snapshot differs from its actual selected source/actor")
            versions = await transaction.runtime_versions(await transaction.now())
            job = await transaction.admit_triage(
                Admission(
                    principal.access.account_id, snapshot.task, command.intent_key, digest, versions
                ),
                await transaction.now(),
            )
            proof = await transaction.record_triage_submission(snapshot, job, uuid4())
            result = await triage_view(
                transaction, StoredReportTriage(job, snapshot, proof), command.report_id
            )
            await finish_operator(transaction, principal)
            return result


@dataclass(frozen=True, slots=True)
class ReportTriageRead:
    report_id: UUID
    triage: ReportTriageView | None = field(repr=False)


@dataclass(frozen=True, slots=True)
class ReadReportTriage:
    unit_of_work: OperatorReportTriageUnitOfWork
    hasher: SessionHasher

    async def __call__(
        self, credential: SessionCredential, report_id: UUID
    ) -> ReportTriageRead | None:
        digest = await self.hasher.digest(credential)
        async with self.unit_of_work.transaction(digest, report_id) as transaction:
            principal = await require_operator(transaction, credential, self.hasher)
            preview = await transaction.lock_triage_context(report_id)
            if preview is not None and preview.report.id != report_id:
                raise RuntimeError("Triage read differs from its actual report source")
            stored = await transaction.latest_triage(report_id) if preview is not None else None
            result = (
                await triage_view(transaction, stored, report_id) if stored is not None else None
            )
            await audit_triage_read(transaction, principal.access, report_id, preview is not None)
            await finish_operator(transaction, principal)
            return ReportTriageRead(report_id, result) if preview is not None else None
