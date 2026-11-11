from dataclasses import replace
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import DateTime, cast, event, func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

import studymate.infrastructure.persistence.discovery_deck as deck_module
from studymate.application.discovery.cursors import DiscoveryView
from studymate.application.discovery.deck import (
    DISCOVERY_PAGE_SIZE,
    DiscoveryEmptyReason,
    ReadDiscoveryDeck,
)
from studymate.application.idempotency import IntentKey
from studymate.application.profiles.goals import CompleteGoalCommand, CompleteOwnGoal
from studymate.application.profiles.help_subjects import SavedHelpSubjects
from studymate.application.requests.actions import AcceptRequest, RequestAction
from studymate.application.requests.ports import RequestPreview, SentRequest
from studymate.application.requests.send import PreviewRequest, SendRequest
from studymate.domain.discovery import DiscoveryMode
from studymate.domain.requests.context import RequestText
from studymate.domain.study_context import HelpSubject, HelpSubjects
from studymate.infrastructure.persistence.discovery_deck import SqlDiscoveryDeckUnitOfWork
from studymate.infrastructure.persistence.discovery_freshness_models import DiscoveryExposureRecord
from studymate.infrastructure.persistence.discovery_query import DiscoveryQuery
from studymate.infrastructure.persistence.goals import SqlGoalUnitOfWork
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    InstitutionalBindingRecord,
)
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import record_request_outcome
from studymate.infrastructure.persistence.profile_sources import read_help_versions
from studymate.infrastructure.requests.transactions import SqlRequestUnitOfWork
from studymate.infrastructure.security.discovery_cursor import FernetDiscoveryCursorCodec
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.integration.discovery_fixture import additional_helper, canonical_goal, discovery_actors
from tests.integration.profile_lifecycle_fixture import command as visibility_command
from tests.integration.profile_lifecycle_fixture import services as visibility_services
from tests.integration.test_discovery_passes import service as pass_service
from tests.integration.test_discovery_passes import submission, submission_owner
from tests.integration.test_help_subjects import command as help_command
from tests.integration.test_help_subjects import services as help_services

pytestmark = pytest.mark.integration


def reader(engine: AsyncEngine) -> ReadDiscoveryDeck:
    return ReadDiscoveryDeck(
        SqlDiscoveryDeckUnitOfWork(async_sessionmaker(engine, expire_on_commit=False)),
        Sha256SessionHasher(),
        FernetDiscoveryCursorCodec.from_key(bytes.fromhex("01" * 32)),
    )


async def test_real_candidate_bulk_projection_has_grounded_profile_and_relevance(
    identity_engine: AsyncEngine,
) -> None:
    send = await submission(identity_engine)
    result = await reader(identity_engine)(send.credential, DiscoveryMode.FIND_HELP)
    assert result.context is not None
    assert result.context.scope == send.context
    assert [card.profile.account_id for card in result.people] == [send.target_id]
    assert result.people[0].match.reason.value == "can_help"
    assert result.people[0].own_pass is None
    assert result.undo_pass is None
    assert result.next_cursor is None
    assert result.empty_reason is None


async def test_real_pass_review_and_undo_projection_survive_new_reader_instances(
    identity_engine: AsyncEngine,
) -> None:
    send = await submission(identity_engine)
    first = await pass_service(identity_engine)(send)
    ordinary = await reader(identity_engine)(send.credential, DiscoveryMode.FIND_HELP)
    assert not ordinary.people
    assert ordinary.empty_reason == DiscoveryEmptyReason.EXHAUSTED
    assert ordinary.undo_pass == first
    review = await reader(identity_engine)(
        send.credential, DiscoveryMode.FIND_HELP, DiscoveryView.PASSED
    )
    assert [card.profile.account_id for card in review.people] == [send.target_id]
    assert review.people[0].own_pass == first
    await pass_service(identity_engine)(
        replace(
            send, passed=False, expected_version=first.version, intent_key=IntentKey(str(uuid4()))
        )
    )
    restored = await reader(identity_engine)(send.credential, DiscoveryMode.FIND_HELP)
    assert restored.people[0].own_pass is not None
    assert not restored.people[0].own_pass.passed
    assert restored.undo_pass is None
    review = await reader(identity_engine)(
        send.credential, DiscoveryMode.FIND_HELP, DiscoveryView.PASSED
    )
    assert not review.people
    assert review.empty_reason == DiscoveryEmptyReason.NO_AVAILABLE_PASSED_PEOPLE


@pytest.mark.parametrize("state", ["banned", "deleted", "unverified", "paused"])
async def test_current_lifecycle_and_exposure_are_excluded_by_real_sql(
    identity_engine: AsyncEngine, state: str
) -> None:
    send = await submission(identity_engine)
    async with async_sessionmaker(identity_engine).begin() as session:
        if state in {"banned", "deleted"}:
            column = AccountRecord.banned_at if state == "banned" else AccountRecord.deleted_at
            await session.execute(
                update(AccountRecord)
                .where(AccountRecord.id == send.target_id)
                .values({column: func.clock_timestamp()})
            )
        elif state == "unverified":
            await session.execute(
                update(InstitutionalBindingRecord)
                .where(InstitutionalBindingRecord.account_id == send.target_id)
                .values(revoked_at=func.clock_timestamp())
            )
        else:
            await session.execute(
                update(DiscoveryExposureRecord)
                .where(DiscoveryExposureRecord.account_id == send.target_id)
                .values(paused_at=func.clock_timestamp())
            )
    result = await reader(identity_engine)(send.credential, DiscoveryMode.FIND_HELP)
    assert not result.people
    assert result.empty_reason == DiscoveryEmptyReason.NO_RELEVANT_PEOPLE


async def test_read_does_not_warm_exposure_or_create_canonical_events(
    identity_engine: AsyncEngine,
) -> None:
    send = await submission(identity_engine)
    sessions = async_sessionmaker(identity_engine)
    async with sessions() as session:
        before = await session.scalar(
            select(DiscoveryExposureRecord.last_activity_at).where(
                DiscoveryExposureRecord.account_id == await submission_owner(identity_engine, send)
            )
        )
        count = await session.scalar(select(func.count()).select_from(ProductEventRecord))
    await reader(identity_engine)(send.credential, DiscoveryMode.FIND_HELP)
    async with sessions() as session:
        after = await session.scalar(
            select(DiscoveryExposureRecord.last_activity_at).where(
                DiscoveryExposureRecord.account_id == await submission_owner(identity_engine, send)
            )
        )
        assert after == before
        assert await session.scalar(select(func.count()).select_from(ProductEventRecord)) == count


async def test_offer_help_works_after_own_goal_completion_without_role_inference(
    identity_engine: AsyncEngine,
) -> None:
    setup = await discovery_actors(identity_engine)
    save_help, _ = help_services(identity_engine)
    await save_help(help_command(setup.viewer, HelpSubjects((HelpSubject(setup.subject.id),))))
    await canonical_goal(identity_engine, setup.target, setup.subject.id)
    uow = SqlGoalUnitOfWork(async_sessionmaker(identity_engine, expire_on_commit=False))
    await CompleteOwnGoal(uow, Sha256SessionHasher(), HmacIntentFingerprinter(bytes(range(32))))(
        CompleteGoalCommand(
            setup.viewer.credential,
            setup.goal.goal.id,
            setup.goal.goal.version,
            IntentKey(str(uuid4())),
        )
    )
    result = await reader(identity_engine)(setup.viewer.credential, DiscoveryMode.OFFER_HELP)
    assert [card.profile.account_id for card in result.people] == [setup.target.id]
    assert result.people[0].match.reason.value == "you_can_help"
    assert result.context is not None
    assert result.context.goal_id is None
    assert result.context.help_version == 1


async def test_study_together_requires_both_actual_shared_preferences(
    identity_engine: AsyncEngine,
) -> None:
    setup = await discovery_actors(identity_engine)
    await canonical_goal(identity_engine, setup.viewer, setup.subject.id, shared=True)
    await canonical_goal(identity_engine, setup.target, setup.subject.id, shared=True)
    result = await reader(identity_engine)(setup.viewer.credential, DiscoveryMode.STUDY_TOGETHER)
    assert [card.profile.account_id for card in result.people] == [setup.target.id]
    assert result.people[0].match.reason.value == "shared_goal"
    await canonical_goal(identity_engine, setup.target, setup.subject.id, shared=False)
    assert not (
        await reader(identity_engine)(setup.viewer.credential, DiscoveryMode.STUDY_TOGETHER)
    ).people


async def test_unicode_topic_match_precedes_fresher_subject_only_candidate(
    identity_engine: AsyncEngine,
) -> None:
    setup = await discovery_actors(identity_engine)
    await canonical_goal(identity_engine, setup.viewer, setup.subject.id, topic="Straße JOINs")
    matching = await additional_helper(identity_engine, setup.subject.id, topic="STRASSE joins")
    async with async_sessionmaker(identity_engine).begin() as session:
        now = (
            await session.execute(select(cast(func.clock_timestamp(), DateTime(timezone=True))))
        ).scalar_one()
        earlier = now - timedelta(days=1)
        await session.execute(
            update(DiscoveryExposureRecord)
            .where(DiscoveryExposureRecord.account_id == matching.id)
            .values(last_activity_at=earlier, confirmed_at=earlier)
        )
    result = await reader(identity_engine)(setup.viewer.credential, DiscoveryMode.FIND_HELP)
    assert [card.profile.account_id for card in result.people] == [matching.id, setup.target.id]
    assert result.people[0].match.same_topic
    assert not result.people[1].match.same_topic


async def test_keyset_pages_are_complete_and_query_count_is_constant(
    identity_engine: AsyncEngine,
) -> None:
    setup = await discovery_actors(identity_engine)
    other_helpers = tuple(
        [
            await additional_helper(identity_engine, setup.subject.id)
            for _ in range(DISCOVERY_PAGE_SIZE)
        ]
    )
    statements: list[str] = []

    def count(*arguments: object) -> None:
        statement = arguments[2]
        if isinstance(statement, str) and statement.startswith("SELECT"):
            statements.append(statement)

    event.listen(identity_engine.sync_engine, "before_cursor_execute", count)
    try:
        first = await reader(identity_engine)(setup.viewer.credential, DiscoveryMode.FIND_HELP)
        first_queries = len(statements)
        statements.clear()
        assert first.next_cursor is not None
        second = await reader(identity_engine)(
            setup.viewer.credential, DiscoveryMode.FIND_HELP, cursor=first.next_cursor
        )
        assert len(statements) == first_queries
    finally:
        event.remove(identity_engine.sync_engine, "before_cursor_execute", count)
    expected = {setup.target.id, *(owner.id for owner in other_helpers)}
    actual = tuple(card.profile.account_id for card in first.people + second.people)
    assert len(actual) == len(expected)
    assert actual == tuple(sorted(expected))
    assert len(first.people) == DISCOVERY_PAGE_SIZE
    assert second.next_cursor is None
    assert first.context is not None
    async with identity_engine.connect() as connection:
        at = (
            await connection.execute(select(cast(func.clock_timestamp(), DateTime(timezone=True))))
        ).scalar_one()
        statement = DiscoveryQuery(first.context, DiscoveryView.CANDIDATES, at, at).statement(
            DISCOVERY_PAGE_SIZE + 1
        )
        compiled = statement.compile(dialect=identity_engine.dialect)
        assert compiled.positiontup is not None
        parameters: tuple[object, ...] = tuple(
            compiled.params[name] for name in compiled.positiontup
        )
        execution: object = (
            await connection.exec_driver_sql(
                "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + str(compiled), parameters
            )
        ).scalar_one()
    assert isinstance(execution, list)
    assert len(execution) == 1
    root: object = execution[0]
    assert isinstance(root, dict)
    plan: object = root.get("Plan")
    assert isinstance(plan, dict)
    assert plan["Node Type"] == "Limit"
    assert plan["Actual Rows"] == DISCOVERY_PAGE_SIZE + 1


@pytest.mark.parametrize("accept", [False, True])
async def test_actual_pending_and_accepted_relationships_are_excluded(
    identity_engine: AsyncEngine, accept: bool
) -> None:
    setup = await discovery_actors(identity_engine)
    uow = SqlRequestUnitOfWork(
        async_sessionmaker(identity_engine, expire_on_commit=False), record_request_outcome
    )
    hasher = Sha256SessionHasher()
    fingerprinter = HmacIntentFingerprinter(bytes(range(32)))
    preview = await PreviewRequest(uow, hasher, fingerprinter)(
        setup.viewer.credential, setup.target.id, DiscoveryMode.FIND_HELP, IntentKey(str(uuid4()))
    )
    assert isinstance(preview, RequestPreview)
    sent = await SendRequest(uow, hasher, fingerprinter)(
        setup.viewer.credential,
        setup.target.id,
        preview.id,
        RequestText("Reviewed synthetic request"),
        IntentKey(str(uuid4())),
    )
    assert isinstance(sent, SentRequest)
    if accept:
        await AcceptRequest(uow, hasher, fingerprinter)(
            RequestAction(
                setup.target.credential,
                setup.viewer.id,
                sent.request.id,
                sent.request.version,
                IntentKey(str(uuid4())),
            )
        )
    result = await reader(identity_engine)(setup.viewer.credential, DiscoveryMode.FIND_HELP)
    assert not result.people


async def test_real_new_request_send_invalidates_latest_pass_undo(
    identity_engine: AsyncEngine,
) -> None:
    send = await submission(identity_engine)
    first = await pass_service(identity_engine)(send)
    assert (
        await reader(identity_engine)(send.credential, DiscoveryMode.FIND_HELP)
    ).undo_pass == first
    uow = SqlRequestUnitOfWork(
        async_sessionmaker(identity_engine, expire_on_commit=False), record_request_outcome
    )
    hasher = Sha256SessionHasher()
    fingerprinter = HmacIntentFingerprinter(bytes(range(32)))
    preview = await PreviewRequest(uow, hasher, fingerprinter)(
        send.credential, send.target_id, DiscoveryMode.FIND_HELP, IntentKey(str(uuid4()))
    )
    assert isinstance(preview, RequestPreview)
    await SendRequest(uow, hasher, fingerprinter)(
        send.credential,
        send.target_id,
        preview.id,
        RequestText("Explicit send after private decision"),
        IntentKey(str(uuid4())),
    )
    result = await reader(identity_engine)(send.credential, DiscoveryMode.FIND_HELP)
    assert result.undo_pass is None


async def test_bulk_help_is_bound_to_the_disclosed_candidate_snapshot_before_concurrent_hide(
    identity_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = await discovery_actors(identity_engine)
    original = read_help_versions
    hidden_topic = "Synthetic new private topic after hiding"

    async def change_before_bulk_help(
        session: AsyncSession, versions: tuple[tuple[UUID, int], ...]
    ) -> dict[UUID, SavedHelpSubjects]:
        visibility, _ = visibility_services(identity_engine)
        await visibility(visibility_command(setup.target))
        save, _ = help_services(identity_engine)
        await save(
            help_command(
                setup.target,
                HelpSubjects((HelpSubject(setup.subject.id, hidden_topic),)),
                version=1,
            )
        )
        return await original(session, versions)

    monkeypatch.setattr(deck_module, "read_help_versions", change_before_bulk_help)
    page = await reader(identity_engine)(setup.viewer.credential, DiscoveryMode.FIND_HELP)
    assert page.people
    assert page.people[0].help_subjects is not None
    assert page.people[0].help_subjects.revision.subjects.values[0].topic_note is None
