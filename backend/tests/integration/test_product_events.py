from datetime import UTC, datetime
from http import HTTPStatus
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.idempotency import IntentKey
from studymate.application.profiles.goals import (
    CompleteGoalCommand,
    CompleteOwnGoal,
    GoalVersionConflictError,
    SavedGoal,
    SaveGoalCommand,
    SaveOwnGoal,
)
from studymate.domain.identity import StudentEmail
from studymate.domain.study_context import CustomSubjectRef, GoalContent, StudyGoal
from studymate.infrastructure.persistence.email_verification import SqlEmailUnitOfWork
from studymate.infrastructure.persistence.goal_models import GoalRecord, GoalRevisionRecord
from studymate.infrastructure.persistence.goals import SqlGoalUnitOfWork
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.integration.http_identity import BrowserHarness, verified, write_headers
from tests.integration.profile_lifecycle_fixture import activated, command, services
from tests.integration.student_actor import actor

pytestmark = pytest.mark.integration
PRIVATE = "Private goal subject and topic never copied into event storage"


async def test_goal_events_follow_committed_revisions_not_retries_or_failed_attempts(
    identity_engine: AsyncEngine,
) -> None:
    owner = await actor(identity_engine)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    uow = SqlGoalUnitOfWork(sessions)
    hasher = Sha256SessionHasher()
    fingerprint = HmacIntentFingerprinter(bytes(range(32)))
    save = SaveOwnGoal(uow, hasher, fingerprint)
    submitted = SaveGoalCommand(
        owner.credential,
        GoalContent(CustomSubjectRef(PRIVATE), topic=PRIVATE),
        None,
        0,
        IntentKey(str(uuid4())),
    )
    goal = await save(submitted)
    assert await save(submitted) == goal
    with pytest.raises(GoalVersionConflictError):
        await save(
            SaveGoalCommand(owner.credential, submitted.content, None, 0, IntentKey(str(uuid4())))
        )
    no_op = await save(
        SaveGoalCommand(
            owner.credential,
            submitted.content,
            goal.goal.id,
            goal.goal.version,
            IntentKey(str(uuid4())),
        )
    )
    assert no_op == goal
    completed_command = CompleteGoalCommand(
        owner.credential, goal.goal.id, goal.goal.version, IntentKey(str(uuid4()))
    )
    complete = CompleteOwnGoal(uow, hasher, fingerprint)
    closed = await complete(completed_command)
    assert await complete(completed_command) == closed
    async with sessions() as session:
        rows = (
            await session.scalars(
                select(ProductEventRecord).order_by(ProductEventRecord.occurred_at)
            )
        ).all()
        assert [row.kind for row in rows] == ["goal.saved", "goal.completed"]
        assert [row.goal_version for row in rows] == [goal.goal.version, closed.goal.version]
        assert all(row.account_id == owner.id and row.goal_id == goal.goal.id for row in rows)
        assert all(row.topic_present and not row.shared_learning for row in rows)
        assert all(row.subject_id is None for row in rows)
        history = (await session.scalars(select(GoalRevisionRecord))).all()
        assert all(row.topic == PRIVATE and row.subject_label == PRIVATE for row in history)
    assert not {"content", "payload", "topic", "context", "email", "display_name"} & set(
        ProductEventRecord.__table__.columns.keys()
    )


async def test_event_and_business_revision_roll_back_together(identity_engine: AsyncEngine) -> None:
    owner = await actor(identity_engine)
    now = datetime.now(UTC)
    uow = SqlGoalUnitOfWork(async_sessionmaker(identity_engine, expire_on_commit=False))

    async def interrupted_write() -> None:
        async with uow.transaction() as transaction:
            await transaction.save_goal(
                SavedGoal(
                    StudyGoal(
                        uuid4(), owner.id, 1, GoalContent(CustomSubjectRef(PRIVATE)), now, now
                    ),
                    PRIVATE,
                )
            )
            raise RuntimeError("Synthetic transaction interruption")

    with pytest.raises(RuntimeError, match="Synthetic transaction interruption"):
        await interrupted_write()
    async with async_sessionmaker(identity_engine)() as session:
        assert (
            await session.scalars(select(func.count()).select_from(ProductEventRecord))
        ).one() == 0
        assert (await session.scalars(select(func.count()).select_from(GoalRecord))).one() == 0


async def test_ready_and_visibility_events_are_once_only_and_retain_initial_actor(
    identity_engine: AsyncEngine,
) -> None:
    owner = await activated(identity_engine)
    change, _ = services(identity_engine)
    submitted = command(owner)
    hidden = await change(submitted)
    assert await change(submitted) == hidden
    assert await change(command(owner, version=hidden.visibility_version)) == hidden
    restored = await change(command(owner, hidden=False, version=hidden.visibility_version))
    async with async_sessionmaker(identity_engine)() as session:
        rows = (
            await session.scalars(
                select(ProductEventRecord).order_by(ProductEventRecord.occurred_at)
            )
        ).all()
        assert [row.kind for row in rows] == [
            "profile.saved",
            "goal.saved",
            "photo.published",
            "profile.ready",
            "profile.hidden",
            "profile.restored",
        ]
        assert next(row for row in rows if row.kind == "profile.saved").profile_version == 1
        assert next(row for row in rows if row.kind == "photo.published").photo_version == 1
        assert all(row.account_id == owner.id for row in rows)
        ready = next(row for row in rows if row.kind == "profile.ready")
        assert ready.profile_version == 1
        assert ready.onboarding_task == "find_help"
        assert [row.visibility_version for row in rows if row.visibility_version is not None] == [
            hidden.visibility_version,
            restored.visibility_version,
        ]
        assert all(row.request_id is None and row.trace_id is None for row in rows)


async def test_membership_event_is_only_written_for_actual_first_binding(
    identity_engine: AsyncEngine,
) -> None:
    owner = await actor(identity_engine, verified=False)
    other = await actor(identity_engine, verified=False)
    uow = SqlEmailUnitOfWork(async_sessionmaker(identity_engine, expire_on_commit=False))
    email = StudentEmail("synthetic-events@mail.apu.edu.my")
    async with uow.transaction() as transaction:
        assert await transaction.bind_membership(owner.id, email, datetime.now(UTC))
    async with uow.transaction() as transaction:
        assert not await transaction.bind_membership(owner.id, email, datetime.now(UTC))
        assert not await transaction.bind_membership(other.id, email, datetime.now(UTC))
    async with async_sessionmaker(identity_engine)() as session:
        events = (await session.scalars(select(ProductEventRecord))).all()
        assert len(events) == 1
        assert events[0].kind == "auth.email_confirmed"
        assert events[0].account_id == owner.id


async def test_database_rejects_incomplete_ready_event_including_null_task(
    identity_engine: AsyncEngine,
) -> None:
    owner = await activated(identity_engine)
    with pytest.raises(IntegrityError):
        async with async_sessionmaker(identity_engine).begin() as session:
            session.add(
                ProductEventRecord(
                    id=uuid4(),
                    account_id=owner.id,
                    kind="profile.ready",
                    occurrence_key="synthetic-malformed",
                    schema_version=1,
                    occurred_at=datetime.now(UTC),
                    profile_version=1,
                    onboarding_task=None,
                )
            )


async def test_http_event_preserves_first_actor_action_and_request_on_lost_response_retry(
    browser: BrowserHarness, identity_engine: AsyncEngine
) -> None:
    account_id = await verified(browser, identity_engine)
    headers = await write_headers(browser.client)
    action_id = uuid4()
    headers["X-Action-ID"] = str(action_id)
    payload = {"subject": {"kind": "custom", "label": PRIVATE}, "expected_version": 0}
    first = await browser.client.put("/api/v1/me/goal", json=payload, headers=headers)
    assert first.status_code == HTTPStatus.OK
    headers["X-Action-ID"] = str(uuid4())
    repeated = await browser.client.put("/api/v1/me/goal", json=payload, headers=headers)
    assert repeated.json() == first.json()
    async with async_sessionmaker(identity_engine)() as session:
        events = (await session.scalars(select(ProductEventRecord))).all()
        assert len(events) == 1
        assert events[0].request_id == UUID(first.headers["x-request-id"])
        assert events[0].action_id == action_id
        assert events[0].account_id == account_id
        assert events[0].goal_id == UUID(first.json()["id"])
        assert events[0].trace_id is None
        assert events[0].span_id is None
