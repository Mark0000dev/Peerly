import asyncio
from dataclasses import replace
from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from studymate.application.feedback.ports import (
    FeedbackVersionConflictError,
    WorkedConfirmationRequiredError,
)
from studymate.application.idempotency import IdempotencyConflictError
from studymate.application.identity.sessions import StudentActionDeniedError, UnauthenticatedError
from studymate.domain.feedback.assessments import FeedbackRevision, StudyAgain
from studymate.domain.feedback.outcomes import StudyAnswer, StudyOutcomeRevision, StudyPromptReceipt
from studymate.infrastructure.feedback.models import (
    FeedbackCommandIntentRecord,
    PeerFeedbackRecord,
    PeerFeedbackRevisionRecord,
    StudyOutcomeRevisionRecord,
    StudyPromptReceiptRecord,
)
from studymate.infrastructure.feedback.transactions import SqlFeedbackUnitOfWork
from studymate.infrastructure.persistence.identity_models import AccountRecord, SessionRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.requests.models import RequestRevisionRecord
from tests.integration.feedback.fixture import RECORDERS, FeedbackServices, prepared

pytestmark = pytest.mark.integration
TWO_REVISIONS = 2


async def test_independent_latest_answers_keep_original_intents_and_events(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    command = api.outcome()
    first = await api.outcomes()(command)
    peer = await api.outcomes()(api.outcome(owner=api.chat.recipient, answer=StudyAnswer.NOT_YET))
    later = await api.outcomes()(api.outcome(version=1, answer=StudyAnswer.DID_NOT_WORK_OUT))
    assert await api.outcomes()(command) == first
    assert await api.read_outcome()(api.chat.sender.credential, api.chat.conversation_id) == later
    assert await api.read_outcome()(api.chat.recipient.credential, api.chat.conversation_id) == peer
    with pytest.raises(IdempotencyConflictError):
        await api.outcomes()(replace(command, answer=StudyAnswer.NOT_YET))
    async with api.chat.api.sessions() as session:
        revisions = tuple(await session.scalars(select(StudyOutcomeRevisionRecord)))
        events = tuple(
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind == "study.reported")
            )
        )
        assert len(revisions) == len((first, peer, later))
        assert len(events) == len(revisions)
        assert {row.study_answer for row in events} == {answer.value for answer in StudyAnswer}


async def test_private_offplatform_feedback_only_promotes_on_explicit_new_revision(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    yes = await api.outcomes()(api.outcome())
    command = api.review()
    private = await api.feedback()(command)
    assert private.worked_confirmation == yes
    assert not private.aggregate_eligible
    await api.exchange()
    # Later traffic cannot mutate the original immutable assessment/intent evidence.
    assert await api.feedback()(command) == private
    read = await api.read_feedback()(api.chat.sender.credential, api.chat.conversation_id)
    assert read is not None
    assert read.revision == private
    public = await api.feedback()(api.review(version=1, again=StudyAgain.NO))
    assert public.id == private.id
    assert public.aggregate_eligible
    await api.chat.send()(api.chat.command())
    assert await api.feedback()(command) == private
    read = await api.read_feedback()(api.chat.sender.credential, api.chat.conversation_id)
    assert read is not None
    assert read.revision == public
    async with api.chat.api.sessions() as session:
        roots = tuple(await session.scalars(select(PeerFeedbackRecord)))
        assert len(roots) == 1
        revisions = tuple(await session.scalars(select(PeerFeedbackRevisionRecord)))
        assert len(revisions) == TWO_REVISIONS
        assert {row.again for row in revisions} == {"yes", "no"}
        assert all(row.team_note == "Synthetic private team note" for row in revisions)
        events = tuple(
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind == "feedback.saved")
            )
        )
        assert len(events) == TWO_REVISIONS


async def test_feedback_needs_own_yes_not_partner_yes_or_system_context(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    await api.outcomes()(api.outcome(owner=api.chat.recipient))
    with pytest.raises(WorkedConfirmationRequiredError):
        await api.feedback()(api.review())
    await api.outcomes()(api.outcome())
    await api.chat.send()(api.chat.command())
    private = await api.feedback()(api.review())
    assert not private.aggregate_eligible
    assert private.interaction.low_message is None or private.interaction.high_message is None


async def test_concurrent_same_intent_is_once_and_distinct_stale_cas_conflicts(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    command = api.outcome()
    first, replay = await asyncio.gather(api.outcomes()(command), api.outcomes()(command))
    assert first == replay
    results = await asyncio.gather(
        api.outcomes()(api.outcome(version=1, answer=StudyAnswer.NOT_YET)),
        api.outcomes()(api.outcome(version=1, answer=StudyAnswer.DID_NOT_WORK_OUT)),
        return_exceptions=True,
    )
    assert sum(isinstance(result, FeedbackVersionConflictError) for result in results) == 1
    assert sum(isinstance(result, StudyOutcomeRevision) for result in results) == 1
    async with api.chat.api.sessions() as session:
        assert (
            len(tuple(await session.scalars(select(StudyOutcomeRevisionRecord)))) == TWO_REVISIONS
        )


async def test_actor_ban_denies_saved_intent_but_deleted_target_does_not_erase_feedback(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    command = api.outcome()
    first = await api.outcomes()(command)
    async with api.chat.api.sessions.begin() as session:
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == api.chat.recipient.id)
            .values(deleted_at=func.clock_timestamp())
        )
    assert await api.outcomes()(command) == first
    assert not (await api.feedback()(api.review())).aggregate_eligible
    async with api.chat.api.sessions.begin() as session:
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == api.chat.sender.id)
            .values(banned_at=func.clock_timestamp())
        )
    with pytest.raises(StudentActionDeniedError):
        await api.outcomes()(command)


async def make_old_acceptance(api: FeedbackServices) -> None:
    async with api.chat.api.sessions.begin() as session:
        now = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        await session.execute(
            update(RequestRevisionRecord)
            .where(
                RequestRevisionRecord.conversation_id == api.chat.conversation_id,
                RequestRevisionRecord.state == "accepted",
            )
            .values(changed_at=now - timedelta(hours=25))
        )


async def test_explicit_later_visit_once_and_nooffer_replay_stays_original(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    await api.exchange()
    early = api.visit()
    assert await api.prompts()(early) is None
    await make_old_acceptance(api)
    assert await api.prompts()(early) is None
    command = api.visit()
    receipt = await api.prompts()(command)
    assert receipt is not None
    assert await api.prompts()(command) == receipt
    assert await api.prompts()(api.visit()) is None
    async with api.chat.api.sessions() as session:
        assert len(tuple(await session.scalars(select(StudyPromptReceiptRecord)))) == 1
        assert (
            len(
                tuple(
                    await session.scalars(
                        select(ProductEventRecord).where(
                            ProductEventRecord.kind == "study.prompt_offered"
                        )
                    )
                )
            )
            == 1
        )


@pytest.mark.parametrize("kind", ["outcome", "feedback", "prompt"])
async def test_required_canonical_failure_rolls_back_business_and_intent(
    identity_engine: AsyncEngine, kind: str
) -> None:
    api = await prepared(identity_engine)
    if kind == "feedback":
        await api.outcomes()(api.outcome())
    if kind == "prompt":
        await api.exchange()
        await make_old_acceptance(api)
    before = await counts(api)

    async def fail_outcome(session: AsyncSession, revision: StudyOutcomeRevision) -> None:
        await RECORDERS.outcome(session, revision)
        raise RuntimeError("synthetic canonical failure")

    async def fail_feedback(session: AsyncSession, revision: FeedbackRevision) -> None:
        await RECORDERS.assessment(session, revision)
        raise RuntimeError("synthetic canonical failure")

    async def fail_prompt(session: AsyncSession, receipt: StudyPromptReceipt) -> None:
        await RECORDERS.prompt(session, receipt)
        raise RuntimeError("synthetic canonical failure")

    callbacks = replace(
        RECORDERS, outcome=fail_outcome, assessment=fail_feedback, prompt=fail_prompt
    )
    failing = replace(api, uow=SqlFeedbackUnitOfWork(api.chat.api.sessions, callbacks))
    with pytest.raises(RuntimeError, match="synthetic canonical failure"):
        await execute(failing, kind)
    assert await counts(api) == before


async def execute(api: FeedbackServices, kind: str) -> None:
    if kind == "outcome":
        await api.outcomes()(api.outcome())
    elif kind == "feedback":
        await api.feedback()(api.review())
    else:
        await api.prompts()(api.visit())


async def counts(api: FeedbackServices) -> tuple[int, ...]:
    models = (
        StudyOutcomeRevisionRecord,
        PeerFeedbackRevisionRecord,
        StudyPromptReceiptRecord,
        FeedbackCommandIntentRecord,
        ProductEventRecord,
    )
    async with api.chat.api.sessions() as session:
        totals = [len(tuple(await session.scalars(select(model)))) for model in models]
    return tuple(totals)


async def test_final_session_deadline_rolls_back_actual_canonical_and_intent_writes(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    before = await counts(api)
    async with api.chat.api.sessions.begin() as session:
        now = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        await session.execute(
            update(SessionRecord)
            .where(SessionRecord.account_id == api.chat.sender.id)
            .values(expires_at=now + timedelta(seconds=1))
        )

    entered = asyncio.Event()

    async def delayed(session: AsyncSession, revision: StudyOutcomeRevision) -> None:
        await RECORDERS.outcome(session, revision)
        entered.set()
        await session.execute(select(func.pg_sleep(1.1)))

    callbacks = replace(RECORDERS, outcome=delayed)
    failing = replace(api, uow=SqlFeedbackUnitOfWork(api.chat.api.sessions, callbacks))
    with pytest.raises(UnauthenticatedError):
        await failing.outcomes()(failing.outcome())
    assert entered.is_set()
    assert await counts(api) == before
