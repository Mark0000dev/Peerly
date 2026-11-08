from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.application.ai.drafts import draft_snapshot_source
from studymate.application.ai.ports import (
    AiSourceUnavailableError,
    DraftSourceIntent,
    StudentSubmission,
)
from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.sessions import StudentActionDeniedError
from studymate.domain.ai.jobs import Failure, JobState
from studymate.domain.ai.tasks import (
    AiKind,
    ClarifiedGoal,
    ClarifyGoal,
    DraftSnapshotSource,
    GoalTextTarget,
    Source,
    SubjectSuggestions,
    SuggestSubject,
)
from studymate.infrastructure.ai.codec import TASK_CODEC
from studymate.infrastructure.ai.models import AiJobRecord
from studymate.infrastructure.persistence.goal_models import GoalRecord, GoalRevisionRecord
from studymate.infrastructure.persistence.goals import SqlGoalTransaction
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from tests.integration.ai.test_queue import goal, services
from tests.integration.catalogue_fixture import subject
from tests.integration.student_actor import actor

pytestmark = pytest.mark.integration


def draft(text: str = "Synthetic unsaved context") -> StudentSubmission:
    return StudentSubmission(AiKind.CLARIFY_GOAL, DraftSourceIntent(uuid4(), 1), text)


async def test_onboarding_draft_advice_has_private_immutable_input_and_never_creates_goal(
    ai_engine: AsyncEngine,
) -> None:
    owner = await actor(ai_engine)
    api = services(ai_engine)
    submitted = draft()
    accepted = await api.submit(owner.credential, submitted, IntentKey(str(uuid4())))
    assert accepted.task.source == draft_snapshot_source(submitted)
    running = await api.queue.claim()
    assert running is not None
    finished = await api.queue.complete(
        running, ClarifiedGoal("Editable unsaved suggestion"), stopped=True
    )
    assert finished.state == JobState.SUCCEEDED
    assert isinstance(finished.task.source, DraftSnapshotSource)
    assert (await api.read(owner.credential, accepted.id)).task == accepted.task
    async with api.sessions() as session:
        assert (await session.scalars(select(func.count()).select_from(GoalRecord))).one() == 0
        assert (
            await session.scalars(select(func.count()).select_from(GoalRevisionRecord))
        ).one() == 0
        events = tuple(await session.scalars(select(ProductEventRecord)))
        assert len(events) == 1
        assert events[0].ai_job_id == accepted.id
        assert events[0].kind == "ai_job.completed"


async def test_unsaved_topic_advice_leaves_saved_goal_and_other_owners_context_untouched(
    ai_engine: AsyncEngine,
) -> None:
    owner, other = await actor(ai_engine), await actor(ai_engine)
    source = await goal(ai_engine, owner)
    other_source = await goal(ai_engine, other)
    api = services(ai_engine)
    async with api.sessions() as session:
        before = await SqlGoalTransaction(session).active_goal(owner.id)
    # A client draft UUID matching another goal remains ONLY correlation, never a read grant.
    submitted = StudentSubmission(
        AiKind.CLARIFY_GOAL,
        DraftSourceIntent(other_source.id, 1),
        "My explicit topic",
        target=GoalTextTarget.TOPIC,
    )
    accepted = await api.submit(owner.credential, submitted, IntentKey(str(uuid4())))
    assert isinstance(accepted.task, ClarifyGoal)
    assert accepted.task.text == "My explicit topic"
    running = await api.queue.claim()
    assert running is not None
    with pytest.raises(ValueError, match="conform"):
        await api.queue.complete(running, ClarifiedGoal("x" * 81), stopped=True)
    await api.queue.complete(running, ClarifiedGoal("Editable topic"), stopped=True)
    async with api.sessions() as session:
        after = await SqlGoalTransaction(session).active_goal(owner.id)
        assert after == before
        assert after is not None
        assert after.goal.id == source.id
        assert after.goal.version == 1


async def test_unsaved_custom_subject_uses_only_selected_catalogue_ids_and_never_maps_goal(
    ai_engine: AsyncEngine,
) -> None:
    owner = await actor(ai_engine)
    known = await subject(ai_engine)
    api = services(ai_engine)
    submitted = StudentSubmission(
        AiKind.SUGGEST_SUBJECT,
        DraftSourceIntent(uuid4(), 1),
        candidate_ids=(known.id,),
        label="Synthetic unsaved custom",
    )
    with pytest.raises(AiSourceUnavailableError):
        await api.submit(
            owner.credential, replace(submitted, candidate_ids=(uuid4(),)), IntentKey(str(uuid4()))
        )
    accepted = await api.submit(owner.credential, submitted, IntentKey(str(uuid4())))
    assert isinstance(accepted.task, SuggestSubject)
    assert accepted.task.label == submitted.label
    running = await api.queue.claim()
    assert running is not None
    await api.queue.complete(running, SubjectSuggestions((known.id,)), stopped=True)
    async with api.sessions() as session:
        assert await SqlGoalTransaction(session).active_goal(owner.id) is None


async def test_changed_draft_payload_never_replays_or_coalesces_another_intent(
    ai_engine: AsyncEngine,
) -> None:
    owner, other = await actor(ai_engine), await actor(ai_engine)
    api = services(ai_engine)
    submitted = draft()
    key = IntentKey(str(uuid4()))
    original = await api.submit(owner.credential, submitted, key)
    replay = await api.submit(owner.credential, submitted, IntentKey(str(uuid4())))
    assert replay.id == original.id
    with pytest.raises(IdempotencyConflictError):
        await api.submit(owner.credential, replace(submitted, text="Changed"), key)
    with pytest.raises(IdempotencyConflictError):
        await api.submit(owner.credential, replace(submitted, target=GoalTextTarget.TOPIC), key)
    changed = await api.submit(
        owner.credential, replace(submitted, text="Changed"), IntentKey(str(uuid4()))
    )
    assert changed.id != original.id
    assert changed.task.source != original.task.source
    isolated = await api.submit(other.credential, submitted, key)
    assert isolated.id != original.id


async def test_retained_legacy_resource_job_decodes_and_executes_with_original_source(
    ai_engine: AsyncEngine,
) -> None:
    owner = await actor(ai_engine)
    api = services(ai_engine)
    source = await goal(ai_engine, owner)
    accepted = await api.submit(
        owner.credential,
        StudentSubmission(AiKind.CLARIFY_GOAL, source, "Legacy explicit context"),
        IntentKey(str(uuid4())),
    )
    old = '{"source":{"id":"' + str(source.id) + '","version":1},"text":"Legacy explicit context"}'
    async with api.sessions.begin() as session:
        await session.execute(
            update(AiJobRecord)
            .where(AiJobRecord.id == accepted.id)
            .values(input_json=old, prompt="peerly-ai-v1", schema_version="peerly-ai-v1")
        )
    restored = await api.read(owner.credential, accepted.id)
    assert restored.task.source == Source(source.id, 1)
    running = await api.queue.claim()
    assert running is not None
    assert running.versions.schema == "peerly-ai-v1"
    assert (
        await api.queue.complete(running, ClarifiedGoal("Legacy editable advice"), stopped=True)
    ).state == JobState.SUCCEEDED


async def test_server_snapshot_hash_is_revalidated_before_execution(ai_engine: AsyncEngine) -> None:
    owner = await actor(ai_engine)
    api = services(ai_engine)
    accepted = await api.submit(owner.credential, draft(), IntentKey(str(uuid4())))
    assert isinstance(accepted.task, ClarifyGoal)
    assert isinstance(accepted.task.source, DraftSnapshotSource)
    corrupted = replace(accepted.task, source=replace(accepted.task.source, content_hash="0" * 64))
    async with api.sessions.begin() as session:
        await session.execute(
            update(AiJobRecord)
            .where(AiJobRecord.id == accepted.id)
            .values(input_json=TASK_CODEC.dump_json(corrupted).decode())
        )
    assert await api.queue.claim() is None
    failed = await api.read(owner.credential, accepted.id)
    assert failed.state == JobState.FAILED
    assert failed.failure == Failure.STALE_SOURCE


async def test_draft_source_never_bypasses_student_verification(ai_engine: AsyncEngine) -> None:
    unverified = await actor(ai_engine, verified=False)
    api = services(ai_engine)
    with pytest.raises(StudentActionDeniedError):
        await api.submit(unverified.credential, draft(), IntentKey(str(uuid4())))
    async with api.sessions() as session:
        assert (await session.scalars(select(func.count()).select_from(AiJobRecord))).one() == 0
