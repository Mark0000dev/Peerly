from dataclasses import replace
from datetime import timedelta
from uuid import UUID, uuid4

import pytest

from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.operator.ai_jobs import ReadOperatorAiJob, ReadOperatorAiJobs
from studymate.application.operator.ai_ports import OperatorAiFilters, OperatorAiPosition
from studymate.application.operator.authority import OperatorAccessDeniedError
from studymate.application.operator.cursors import InvalidOperatorCursorError, OperatorCursorScope
from studymate.domain.ai.jobs import JobState
from studymate.domain.ai.tasks import AiKind
from studymate.domain.operator.ai_jobs import (
    OPERATOR_AI_INPUT_BYTES,
    OPERATOR_AI_MAX_ATTEMPTS,
    OPERATOR_AI_PAGE_SIZE,
    OPERATOR_AI_RESULT_BYTES,
    OperatorAiAttempt,
    OperatorAiAttemptOutcome,
)
from studymate.domain.operator.audit import OperatorAction, OperatorAuditOutcome
from studymate.infrastructure.operator.ai_cursors import FernetOperatorAiCursorCodec
from studymate.infrastructure.operator.cursors import encode_cursor
from tests.unit.identity_store import CREDENTIAL, NOW
from tests.unit.operator.ai_store import (
    DIGEST,
    JOB,
    RAW_INPUT,
    RAW_RESULT,
    AiStore,
    detail,
    metadata,
)
from tests.unit.operator.store import TARGET
from tests.unit.operator.test_authorized_reads import FINGERPRINTER, HASHER

CODEC = FernetOperatorAiCursorCodec.from_key(b"j" * 32)


def jobs(store: AiStore) -> ReadOperatorAiJobs:
    return ReadOperatorAiJobs(store, HASHER, FINGERPRINTER, CODEC)


def job(store: AiStore) -> ReadOperatorAiJob:
    return ReadOperatorAiJob(store, HASHER)


async def test_operator_without_student_setup_reads_exact_raw_legacy_business_data() -> None:
    store = AiStore()
    store.assign_explicit_operator()
    store.actor = replace(
        store.actor, membership=None, activation_complete=False, registration=None
    )
    listing = await jobs(store)(CREDENTIAL, TARGET, OperatorAiFilters())
    assert listing is not None
    assert not hasattr(listing.jobs[0], "input_json_raw")
    assert not hasattr(listing.jobs[0], "input_digest")
    result = await job(store)(CREDENTIAL, TARGET, JOB)
    assert result is not None
    assert result.detail.input_json_raw == RAW_INPUT
    assert result.detail.result_json_raw == RAW_RESULT
    assert result.detail.input_digest == DIGEST
    assert RAW_INPUT not in repr(result)
    assert RAW_RESULT not in repr(result.detail)
    assert result.detail.job.versions.schema == " unsupported schema "
    assert result.observed_at == NOW
    assert store.audit[-1].action == OperatorAction.READ_ACCOUNT
    assert store.audit[-1].results[0].id == TARGET


async def test_real_parent_container_audit_for_missing_foreign_job_and_missing_account() -> None:
    store = AiStore()
    store.assign_explicit_operator()
    assert await job(store)(CREDENTIAL, TARGET, uuid4()) is None
    parent_read = store.audit[-1]
    assert parent_read.outcome == OperatorAuditOutcome.READ
    assert parent_read.results[0].id == TARGET
    store.job_details[JOB] = detail(account_id=uuid4())
    assert await job(store)(CREDENTIAL, TARGET, JOB) is None
    assert await jobs(store)(CREDENTIAL, uuid4(), OperatorAiFilters()) is None
    unknown = store.audit[-1]
    assert unknown.outcome == OperatorAuditOutcome.NOT_FOUND
    assert not unknown.results
    assert await job(store)(CREDENTIAL, uuid4(), JOB) is None
    store.rows = {}
    empty = await jobs(store)(CREDENTIAL, TARGET, OperatorAiFilters())
    assert empty is not None
    assert empty.jobs == ()
    assert empty.anchor_job_id is None


async def test_metadata_pagination_filters_and_actual_future_anchor_are_not_queue_policy() -> None:
    store = AiStore()
    store.assign_explicit_operator()
    store.rows = {
        UUID(int=i): replace(metadata(UUID(int=i)), created_at=NOW + timedelta(minutes=i))
        for i in range(1, OPERATOR_AI_PAGE_SIZE + 3)
    }
    filters = OperatorAiFilters(AiKind.CLARIFY_GOAL, JobState.SUCCEEDED, created_from=NOW)
    first = await jobs(store)(CREDENTIAL, TARGET, filters)
    assert first is not None
    assert first.next_cursor is not None
    assert len(first.jobs) == OPERATOR_AI_PAGE_SIZE
    assert first.anchor_created_at is not None
    assert first.anchor_created_at > first.observed_at
    newer = replace(metadata(uuid4()), created_at=NOW + timedelta(days=2))
    store.rows[newer.id] = newer
    second = await jobs(store)(CREDENTIAL, TARGET, filters, first.next_cursor)
    assert second is not None
    assert len(second.jobs) == len((1, 2))
    assert second.next_cursor is None
    assert newer not in second.jobs
    with pytest.raises(InvalidOperatorCursorError):
        await jobs(store)(CREDENTIAL, TARGET, OperatorAiFilters(), first.next_cursor)
    upper = await jobs(store)(CREDENTIAL, TARGET, OperatorAiFilters(created_before=NOW))
    assert upper is not None
    assert not upper.jobs
    other = await jobs(store)(CREDENTIAL, TARGET, OperatorAiFilters(AiKind.ASSESS_PHOTO))
    assert other is not None
    assert not other.jobs
    queued = await jobs(store)(CREDENTIAL, TARGET, OperatorAiFilters(state=JobState.QUEUED))
    assert queued is not None
    assert not queued.jobs


@pytest.mark.parametrize("read_detail", [True, False])
async def test_explicit_live_operator_is_required_before_source_reads(read_detail: bool) -> None:
    store = AiStore()
    operation = (
        job(store)(CREDENTIAL, TARGET, JOB)
        if read_detail
        else jobs(store)(CREDENTIAL, TARGET, OperatorAiFilters())
    )
    with pytest.raises(OperatorAccessDeniedError):
        await operation
    assert store.private_queries == 0
    store.assign_explicit_operator()
    store.clock = store.actor.session.expires_at
    operation = (
        job(store)(CREDENTIAL, TARGET, JOB)
        if read_detail
        else jobs(store)(CREDENTIAL, TARGET, OperatorAiFilters())
    )
    with pytest.raises(UnauthenticatedError):
        await operation
    assert not store.audit


@pytest.mark.parametrize("fault", ["owner", "order", "bounds", "filter"])
async def test_list_source_cannot_invent_owner_order_or_unbounded_rows(fault: str) -> None:
    store = AiStore()
    store.assign_explicit_operator()
    row = metadata(account_id=uuid4()) if fault == "owner" else metadata()
    store.list_override = (
        (row, row)
        if fault == "order"
        else (row,) * (OPERATOR_AI_PAGE_SIZE + 2)
        if fault == "bounds"
        else (row,)
    )
    filters = OperatorAiFilters(state=JobState.FAILED) if fault == "filter" else OperatorAiFilters()
    with pytest.raises(RuntimeError, match="source"):
        await jobs(store)(CREDENTIAL, TARGET, filters)
    assert not store.audit


@pytest.mark.parametrize("read_detail", [True, False])
async def test_actual_account_lookup_cannot_substitute_target(read_detail: bool) -> None:
    store = AiStore()
    store.assign_explicit_operator()
    store.account_override = uuid4()
    operation = (
        job(store)(CREDENTIAL, TARGET, JOB)
        if read_detail
        else jobs(store)(CREDENTIAL, TARGET, OperatorAiFilters())
    )
    with pytest.raises(RuntimeError, match="account source"):
        await operation


async def test_detail_owner_and_job_proof_is_not_just_an_arbitrary_source_id() -> None:
    store = AiStore()
    store.assign_explicit_operator()
    store.detail_override = detail(job_id=uuid4())
    with pytest.raises(RuntimeError, match="actual owner or job"):
        await job(store)(CREDENTIAL, TARGET, JOB)


def test_payload_bounds_use_stored_utf8_limits_not_current_task_decoding() -> None:
    original = detail()
    assert replace(original, input_json_raw="é" * (OPERATOR_AI_INPUT_BYTES // 2)).input_json_raw
    assert replace(original, result_json_raw="é" * (OPERATOR_AI_RESULT_BYTES // 2)).result_json_raw
    with pytest.raises(ValueError, match="payload bounds"):
        replace(original, input_json_raw="é" * (OPERATOR_AI_INPUT_BYTES // 2 + 1))
    with pytest.raises(ValueError, match="payload bounds"):
        replace(original, result_json_raw="é" * (OPERATOR_AI_RESULT_BYTES // 2 + 1))
    with pytest.raises(ValueError, match="stored input digest"):
        replace(original, input_digest=b"short")
    with pytest.raises(ValueError, match="positive source version"):
        replace(original.job, source_version=0)
    with pytest.raises(ValueError, match="bounded attempt count"):
        replace(original.job, attempts_count=OPERATOR_AI_MAX_ATTEMPTS + 1)


def test_attempts_are_actual_bounded_current_records_without_token_or_fabricated_id() -> None:
    first = OperatorAiAttempt(JOB, 1, NOW, None, None)
    changed = replace(first, ended_at=NOW, outcome=OperatorAiAttemptOutcome.EXECUTOR_LOST)
    actual = replace(detail(), attempts_current=(changed,))
    assert actual.attempts_current[0].outcome == OperatorAiAttemptOutcome.EXECUTOR_LOST
    assert not hasattr(first, "id")
    assert not hasattr(first, "token")
    with pytest.raises(ValueError, match="bounded attempt number"):
        replace(first, number=0)
    with pytest.raises(ValueError, match="bounded job source"):
        replace(actual, attempts_current=(changed, changed))
    with pytest.raises(ValueError, match="bounded job source"):
        replace(actual, attempts_current=(replace(changed, job_id=uuid4()),))
    with pytest.raises(ValueError, match="bounded job source"):
        replace(actual, attempts_current=(changed,) * (OPERATOR_AI_MAX_ATTEMPTS + 1))


def test_cursor_is_account_actor_grant_filter_and_purpose_bound() -> None:
    scope = OperatorCursorScope(TARGET, 1)
    point = OperatorAiPosition(NOW, JOB, NOW, JOB)
    digest = b"d" * 32
    token = CODEC.encode(scope, TARGET, digest, point)
    assert CODEC.decode(scope, TARGET, digest, token) == point
    for actual, account, query in (
        (OperatorCursorScope(uuid4(), 1), TARGET, digest),
        (OperatorCursorScope(TARGET, 2), TARGET, digest),
        (scope, uuid4(), digest),
        (scope, TARGET, b"x" * 32),
    ):
        with pytest.raises(InvalidOperatorCursorError):
            CODEC.decode(actual, account, query, token)
    malformed = encode_cursor(
        CODEC.roots,
        (
            "operator-ai-jobs-v1",
            str(TARGET),
            "1",
            str(TARGET),
            digest.hex(),
            "bad-date",
            str(JOB),
            NOW.isoformat(),
            str(JOB),
        ),
    )
    with pytest.raises(InvalidOperatorCursorError):
        CODEC.decode(scope, TARGET, digest, malformed)
    with pytest.raises(ValueError, match="configured32-byte"):
        FernetOperatorAiCursorCodec.from_key(b"short")
    with pytest.raises(ValueError, match="actual query HMAC"):
        CODEC.encode(scope, TARGET, b"short", point)
    with pytest.raises(ValueError, match="nonempty half-open"):
        OperatorAiFilters(created_from=NOW, created_before=NOW)
    with pytest.raises(ValueError, match="actual metadata anchor"):
        OperatorAiPosition(NOW, JOB, NOW + timedelta(seconds=1), JOB)
