from dataclasses import replace
from uuid import uuid4

import pytest

from studymate.application.ai.ports import AiQuotaError, AiUnavailableError
from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.operator.authority import OperatorAccessDeniedError
from studymate.application.operator.report_triage import (
    EnqueueReportTriage,
    EnqueueReportTriageCommand,
    ReadReportTriage,
    ReadReportTriageContext,
)
from studymate.application.operator.report_triage_ports import (
    InvalidReportTriageSourceError,
    ReportTriageSourceUnavailableError,
)
from studymate.domain.ai.jobs import JobState
from studymate.domain.ai.tasks import Priority, ReportTriage
from studymate.domain.operator.report_triage import TRIAGE_SOURCE_TOKEN_LIFETIME
from studymate.infrastructure.operator.report_triage_cursors import FernetReportTriageSourceCodec
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from tests.unit.identity_store import CREDENTIAL, NOW
from tests.unit.operator.report_triage.store import REPORT_ID, TriageStore
from tests.unit.operator.test_authorized_reads import HASHER

CODEC = FernetReportTriageSourceCodec.from_key(b"t" * 32)
FINGERPRINTER = HmacIntentFingerprinter(b"t" * 32)


def context_reader(store: TriageStore) -> ReadReportTriageContext:
    return ReadReportTriageContext(store, HASHER, CODEC)


def enqueuer(store: TriageStore) -> EnqueueReportTriage:
    return EnqueueReportTriage(store, HASHER, FINGERPRINTER, CODEC)


async def command(store: TriageStore) -> EnqueueReportTriageCommand:
    context = await context_reader(store)(CREDENTIAL, REPORT_ID)
    assert context is not None
    assert context.source_token is not None
    return EnqueueReportTriageCommand(
        CREDENTIAL, REPORT_ID, context.source_token, IntentKey("triage-intent")
    )


async def test_unverified_operator_can_use_internal_path_without_student_guard_bypass() -> None:
    store = TriageStore()
    store.assign_explicit_operator()
    store.actor = replace(
        store.actor, membership=None, activation_complete=False, registration=None
    )
    request = await command(store)
    audit_count = len(store.audit)
    assert store.jobs == {}
    first = await enqueuer(store)(request)
    assert first.observation.state == JobState.QUEUED
    assert first.observation.priority is None
    assert first.observation.rationale is None
    assert first.submission.operator == store.access
    assert first.submission.actor_session_id == store.actor.session.id
    assert len(store.audit) == audit_count
    assert "Exact private" not in repr(first)
    store.clock += TRIAGE_SOURCE_TOKEN_LIFETIME
    assert await enqueuer(store)(request) == first
    assert len(store.jobs) == 1
    assert len(store.events) == 1


@pytest.mark.parametrize("change", ["evidence", "review", "expired", "session", "grant"])
async def test_new_submission_revalidates_exact_source_and_live_token_claims(change: str) -> None:
    store = TriageStore()
    store.assign_explicit_operator()
    request = await command(store)
    if change == "evidence":
        store.change_evidence()
    elif change == "review":
        assert store.preview is not None
        assert store.preview.context is not None
        store.preview = replace(
            store.preview, context=replace(store.preview.context, review_version=1)
        )
    elif change == "expired":
        store.clock += TRIAGE_SOURCE_TOKEN_LIFETIME
    elif change == "session":
        store.actor = replace(store.actor, session=replace(store.actor.session, id=uuid4()))
    else:
        assert store.access is not None
        store.access = replace(store.access, version=2)
    error = (
        ReportTriageSourceUnavailableError
        if change in {"evidence", "review"}
        else InvalidReportTriageSourceError
    )
    with pytest.raises(error):
        await enqueuer(store)(request)
    assert not store.jobs
    assert not store.snapshots
    assert not store.events


@pytest.mark.parametrize("state", ["absent", "revoked", "banned", "deleted", "expired"])
async def test_no_report_or_queue_access_before_current_operator_authority(state: str) -> None:
    store = TriageStore()
    if state != "absent":
        store.assign_explicit_operator()
    if state == "revoked":
        assert store.access is not None
        store.access = replace(store.access, active=False)
    elif state == "banned":
        store.actor = replace(store.actor, banned=True)
    elif state == "deleted":
        store.actor = replace(store.actor, deleted_at=NOW)
    elif state == "expired":
        store.clock = store.actor.session.expires_at
    error = UnauthenticatedError if state in {"deleted", "expired"} else OperatorAccessDeniedError
    with pytest.raises(error):
        await context_reader(store)(CREDENTIAL, REPORT_ID)
    assert store.private_queries == 0
    assert not store.jobs


@pytest.mark.parametrize("failure", ["queue", "quota", "canonical", "expiry", "commit"])
async def test_failed_admission_never_leaves_fake_pending_job_or_orphan_snapshot(
    failure: str,
) -> None:
    store = TriageStore()
    store.assign_explicit_operator()
    request = await command(store)
    store.queue_full = failure == "queue"
    store.quota = failure == "quota"
    store.fail_canonical = failure == "canonical"
    store.expire_after_admit = failure == "expiry"
    store.fail_commit = failure == "commit"
    error = {
        "queue": AiUnavailableError,
        "quota": AiQuotaError,
        "expiry": UnauthenticatedError,
    }.get(failure, RuntimeError)
    with pytest.raises(error):
        await enqueuer(store)(request)
    assert not store.jobs
    assert not store.snapshots
    assert not store.proofs
    assert not store.intents
    assert not store.events


async def test_completed_outdated_suggestion_is_withheld_without_automatic_moderation() -> None:
    store = TriageStore()
    store.assign_explicit_operator()
    submitted = await enqueuer(store)(await command(store))
    job_id = submitted.observation.job_id
    store.jobs[job_id] = replace(
        store.jobs[job_id],
        state=JobState.SUCCEEDED,
        result=ReportTriage(Priority.HIGH, "Private advisory rationale"),
    )
    store.change_evidence()
    current = await ReadReportTriage(store, HASHER)(CREDENTIAL, REPORT_ID)
    assert current is not None
    assert current.triage is not None
    assert current.triage.observation.state == JobState.SUCCEEDED
    assert current.triage.observation.source_current is False
    assert current.triage.observation.priority is None
    assert current.triage.observation.rationale is None
    assert len(store.events) == 1
    assert store.audit[-1].action.value == "read_report"


async def test_actor_scoped_conflicting_intent_and_existing_untriaged_report_are_truthful() -> None:
    store = TriageStore()
    store.assign_explicit_operator()
    empty = await ReadReportTriage(store, HASHER)(CREDENTIAL, REPORT_ID)
    assert empty is not None
    assert empty.triage is None
    request = await command(store)
    await enqueuer(store)(request)
    another = await command(store)
    with pytest.raises(IdempotencyConflictError):
        await enqueuer(store)(another)
    assert len(store.jobs) == 1
    assert await ReadReportTriage(store, HASHER)(CREDENTIAL, uuid4()) is None
    assert store.audit[-1].outcome.value == "not_found"
