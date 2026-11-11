from dataclasses import replace
from datetime import timedelta
from uuid import UUID, uuid4

import pytest

from studymate.application.errors import StorageUnavailableError
from studymate.application.feedback.assessments import SaveFeedback, SaveFeedbackCommand
from studymate.application.feedback.outcomes import SaveStudyOutcome, StudyOutcomeCommand
from studymate.application.feedback.ports import (
    FeedbackOperation,
    FeedbackVersionConflictError,
    WorkedConfirmationRequiredError,
)
from studymate.application.feedback.prompts import OfferStudyPromptOnVisit, StudyPromptVisitCommand
from studymate.application.feedback.reads import ReadOwnFeedback, ReadOwnStudyOutcome
from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.sessions import StudentActionDeniedError, UnauthenticatedError
from studymate.application.messaging.ports import ConversationUnavailableError
from studymate.domain.feedback.assessments import (
    CurrentFeedback,
    FeedbackContent,
    FeedbackRemoval,
    RemovalKind,
    StudyAgain,
)
from studymate.domain.feedback.interaction import PROMPT_DELAY
from studymate.domain.feedback.outcomes import StudyAnswer, StudyPromptReceipt
from studymate.domain.feedback.summary import summarize_feedback
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.unit.feedback.fixture import feedback, outcome
from tests.unit.feedback.store import Store
from tests.unit.identity_store import CREDENTIAL

HASHER = Sha256SessionHasher()
FP = HmacIntentFingerprinter(b"f" * 32)


def command(
    store: Store, *, answer: StudyAnswer = StudyAnswer.YES, version: int = 0
) -> StudyOutcomeCommand:
    return StudyOutcomeCommand(
        CREDENTIAL, store.source.conversation.id, answer, version, IntentKey(str(uuid4()))
    )


def review(store: Store, *, version: int = 0) -> SaveFeedbackCommand:
    return SaveFeedbackCommand(
        CREDENTIAL,
        store.source.conversation.id,
        FeedbackContent(StudyAgain.YES, team_note="Synthetic private note"),
        version,
        IntentKey(str(uuid4())),
    )


def visit(store: Store) -> StudyPromptVisitCommand:
    return StudyPromptVisitCommand(
        CREDENTIAL, store.source.conversation.id, IntentKey(str(uuid4()))
    )


async def test_independent_outcome_replay_original_and_changedpayload_conflict() -> None:
    store = Store()
    save = SaveStudyOutcome(store, HASHER, FP)
    original = command(store)
    first = await save(original)
    later = await save(command(store, answer=StudyAnswer.NOT_YET, version=1))
    assert later.version == first.version + 1
    assert await save(original) == first
    assert store.outcome_history == [first, later]
    with pytest.raises(IdempotencyConflictError):
        await save(replace(original, answer=StudyAnswer.DID_NOT_WORK_OUT))
    with pytest.raises(FeedbackVersionConflictError) as error:
        await save(command(store))
    assert error.value.current_version == later.version


async def test_feedback_snapshot_retains_historical_yes_and_private_note_not_in_repr() -> None:
    store = Store()
    first_yes = await SaveStudyOutcome(store, HASHER, FP)(command(store))
    save = SaveFeedback(store, HASHER, FP)
    original = review(store)
    first = await save(original)
    assert first.worked_confirmation == first_yes
    assert first.aggregate_eligible
    assert "Synthetic private note" not in repr(first)
    await SaveStudyOutcome(store, HASHER, FP)(
        command(store, answer=StudyAnswer.DID_NOT_WORK_OUT, version=1)
    )
    assert await save(original) == first
    assert store.assessments[first.reviewer_id, first.partner_id].revision == first
    with pytest.raises(WorkedConfirmationRequiredError):
        await save(review(store, version=1))
    with pytest.raises(IdempotencyConflictError):
        await save(replace(original, content=FeedbackContent(StudyAgain.NO)))


async def test_update_replaces_current_pair_once_retains_revisions_and_cas() -> None:
    store = Store()
    await SaveStudyOutcome(store, HASHER, FP)(command(store))
    save = SaveFeedback(store, HASHER, FP)
    first = await save(review(store))
    second = await save(
        replace(review(store, version=1), content=FeedbackContent(StudyAgain.MAYBE))
    )
    assert second.id == first.id
    assert second.version == first.version + 1
    assert len(store.assessments) == 1
    assert store.feedback_history == [first, second]
    with pytest.raises(FeedbackVersionConflictError):
        await save(review(store))


async def test_private_offplatform_eligible_only_on_new_explicit_revision() -> None:
    store = Store()
    complete = store.source
    store.source = replace(complete, high_message=None)
    await SaveStudyOutcome(store, HASHER, FP)(command(store))
    save = SaveFeedback(store, HASHER, FP)
    first = await save(review(store))
    assert not first.aggregate_eligible
    store.source = complete
    assert not store.feedback_history[0].aggregate_eligible
    second = await save(review(store, version=1))
    assert second.aggregate_eligible
    assert not first.aggregate_eligible


async def test_blocked_hidden_unavailable_peer_does_not_remove_history_feedback_access() -> None:
    store = Store()
    assert store.access is not None
    store.access = replace(
        store.access, blocked=True, peer_deleted=True, peer_banned=True, peer_verified=False
    )
    assert not store.access.can_send
    await SaveStudyOutcome(store, HASHER, FP)(command(store))
    assert (await SaveFeedback(store, HASHER, FP)(review(store))).aggregate_eligible


async def test_requires_own_explicit_yes_without_fabricated_publication_role() -> None:
    store = Store()
    with pytest.raises(WorkedConfirmationRequiredError):
        await SaveFeedback(store, HASHER, FP)(review(store))
    await SaveStudyOutcome(store, HASHER, FP)(command(store, answer=StudyAnswer.NOT_YET))
    with pytest.raises(WorkedConfirmationRequiredError):
        await SaveFeedback(store, HASHER, FP)(review(store))


async def test_explicit_visit_once_after24h_and_no_repeated_invitation() -> None:
    store = Store()
    offers = OfferStudyPromptOnVisit(store, HASHER, FP)
    early = visit(store)
    store.clock = store.source.accepted_at + PROMPT_DELAY - timedelta(microseconds=1)
    store.actor = replace(
        store.actor,
        session=replace(store.actor.session, issued_at=store.clock - timedelta(minutes=1)),
    )
    assert await offers(early) is None
    store.clock += timedelta(microseconds=1)
    assert await offers(early) is None
    actual_visit = visit(store)
    first = await offers(actual_visit)
    assert first is not None
    assert await offers(actual_visit) == first
    assert await offers(visit(store)) is None
    assert len(store.prompts) == 1


async def test_no_automatic_prompt_without_two_way_or_after_answer() -> None:
    store = Store()
    offers = OfferStudyPromptOnVisit(store, HASHER, FP)
    source = store.source
    store.source = replace(source, high_message=None)
    assert await offers(visit(store)) is None
    store.source = source
    await SaveStudyOutcome(store, HASHER, FP)(command(store))
    assert await offers(visit(store)) is None
    assert not store.prompts


@pytest.mark.parametrize("kind", ["outcome", "feedback", "visit"])
@pytest.mark.parametrize(
    "fault", ["banned", "deleted", "expired", "unverified", "unactivated", "foreign"]
)
async def test_all_commands_recheck_actual_live_actor_and_conversation(
    kind: str, fault: str
) -> None:
    store = Store()
    if fault == "banned":
        store.actor = replace(store.actor, banned=True)
    elif fault == "deleted":
        store.actor = replace(store.actor, deleted_at=store.clock)
    elif fault == "expired":
        store.clock = store.actor.session.expires_at
    elif fault == "unverified":
        store.actor = replace(store.actor, membership=None)
    elif fault == "unactivated":
        store.actor = replace(store.actor, activation_complete=False)
    else:
        store.access = None
    error = (
        UnauthenticatedError
        if fault in {"deleted", "expired"}
        else ConversationUnavailableError
        if fault == "foreign"
        else StudentActionDeniedError
    )
    with pytest.raises(error):
        await execute(store, kind)
    assert not store.intents
    assert not store.prompts
    assert not store.outcome_history
    assert not store.feedback_history


@pytest.mark.parametrize("kind", ["outcome", "feedback", "visit"])
@pytest.mark.parametrize("fault", ["storage", "deadline"])
async def test_all_mutation_and_intent_writes_roll_back_before_response(
    kind: str, fault: str
) -> None:
    store = Store()
    if kind == "feedback":
        await SaveStudyOutcome(store, HASHER, FP)(command(store))
    original_intents = store.intents.copy()
    original_outcomes = store.outcome_history.copy()
    store.fail_save = fault == "storage"
    store.expire_on_save = fault == "deadline"
    error = StorageUnavailableError if fault == "storage" else UnauthenticatedError
    with pytest.raises(error):
        await execute(store, kind)
    assert store.intents == original_intents
    assert store.outcome_history == original_outcomes
    assert not store.feedback_history
    assert not store.prompts


async def execute(store: Store, kind: str) -> None:
    if kind == "outcome":
        await SaveStudyOutcome(store, HASHER, FP)(command(store))
    elif kind == "feedback":
        await SaveFeedback(store, HASHER, FP)(review(store))
    else:
        await OfferStudyPromptOnVisit(store, HASHER, FP)(visit(store))


async def test_author_edit_cannot_self_clear_moderator_removal() -> None:
    store = Store()
    await SaveStudyOutcome(store, HASHER, FP)(command(store))
    save = SaveFeedback(store, HASHER, FP)
    first = await save(review(store))
    removal = FeedbackRemoval(
        first.id,
        first.version,
        uuid4(),
        RemovalKind.ABUSIVE,
        "Documented synthetic moderation",
        store.clock,
    )
    store.assessments[first.reviewer_id, first.partner_id] = CurrentFeedback(first, removal)
    second = await save(review(store, version=1))
    retained = store.assessments[second.reviewer_id, second.partner_id]
    assert retained.removal == removal
    assert retained.revision == second
    assert second.version > removal.source_version
    assert summarize_feedback(second.partner_id, (retained,)).responses == 0


@pytest.mark.parametrize("bad", [True, -1])
def test_commands_reject_invalid_expected_versions(bad: int) -> None:
    store = Store()
    with pytest.raises(ValueError, match="nonnegative"):
        replace(command(store), expected_version=bad)
    with pytest.raises(ValueError, match="nonnegative"):
        replace(review(store), expected_version=bad)


@pytest.mark.parametrize("kind", ["outcome", "feedback", "visit"])
async def test_saved_intents_never_bypass_later_actor_ban(kind: str) -> None:
    store = Store()
    if kind == "feedback":
        await SaveStudyOutcome(store, HASHER, FP)(command(store))
    outcome_command, feedback_command, visit_command = command(store), review(store), visit(store)

    async def same_intent() -> None:
        if kind == "outcome":
            await SaveStudyOutcome(store, HASHER, FP)(outcome_command)
        elif kind == "feedback":
            await SaveFeedback(store, HASHER, FP)(feedback_command)
        else:
            await OfferStudyPromptOnVisit(store, HASHER, FP)(visit_command)

    await same_intent()
    store.actor = replace(store.actor, banned=True)
    with pytest.raises(StudentActionDeniedError):
        await same_intent()


@pytest.mark.parametrize("kind", ["outcome", "feedback", "visit"])
async def test_malformed_retained_intents_fail_closed_not_wrong_result_type(kind: str) -> None:
    store = Store()
    if kind == "feedback":
        await SaveStudyOutcome(store, HASHER, FP)(command(store))
    outcome_command, feedback_command, visit_command = command(store), review(store), visit(store)
    if kind == "outcome":
        await SaveStudyOutcome(store, HASHER, FP)(outcome_command)
    elif kind == "feedback":
        await SaveFeedback(store, HASHER, FP)(feedback_command)
    else:
        await OfferStudyPromptOnVisit(store, HASHER, FP)(visit_command)
    op = {
        "outcome": FeedbackOperation.STUDY_OUTCOME,
        "feedback": FeedbackOperation.ASSESSMENT,
        "visit": FeedbackOperation.PROMPT_VISIT,
    }[kind]
    keys = [key for key in store.intents if key[1] == op]
    key = keys[-1]
    wrong = outcome(store.source, actor=store.actor.session.account_id) if kind == "visit" else None
    store.intents[key] = replace(store.intents[key], result=wrong)
    with pytest.raises(RuntimeError, match="typed result"):
        await run_same(store, kind, outcome_command, feedback_command, visit_command)


async def run_same(
    store: Store,
    kind: str,
    outcome_command: StudyOutcomeCommand,
    feedback_command: SaveFeedbackCommand,
    visit_command: StudyPromptVisitCommand,
) -> None:
    if kind == "outcome":
        await SaveStudyOutcome(store, HASHER, FP)(outcome_command)
    elif kind == "feedback":
        await SaveFeedback(store, HASHER, FP)(feedback_command)
    else:
        await OfferStudyPromptOnVisit(store, HASHER, FP)(visit_command)


async def test_own_reads_do_not_answer_offer_or_publish_and_retain_access_after_block() -> None:
    store = Store()
    answers = ReadOwnStudyOutcome(store, HASHER)
    reviews = ReadOwnFeedback(store, HASHER)
    conversation_id = store.source.conversation.id
    assert await answers(CREDENTIAL, conversation_id) is None
    assert await reviews(CREDENTIAL, conversation_id) is None
    assert not store.intents
    assert not store.prompts
    yes = await SaveStudyOutcome(store, HASHER, FP)(command(store))
    assessment = await SaveFeedback(store, HASHER, FP)(review(store))
    intents = store.intents.copy()
    assert store.access is not None
    store.access = replace(store.access, blocked=True, peer_deleted=True)
    assert await answers(CREDENTIAL, conversation_id) == yes
    observed = await reviews(CREDENTIAL, conversation_id)
    assert observed is not None
    assert observed.revision == assessment
    assert store.intents == intents
    assert not store.prompts


@pytest.mark.parametrize(
    "source", ["outcome", "assessment", "interaction", "prompt", "prompt_interaction"]
)
async def test_foreign_current_sources_fail_closed_not_become_business_authority(
    source: str,
) -> None:
    store = Store()
    yes = await SaveStudyOutcome(store, HASHER, FP)(command(store))
    assessment = await SaveFeedback(store, HASHER, FP)(review(store))
    actor_id = store.actor.session.account_id
    conversation_id = store.source.conversation.id
    if source == "outcome":
        store.outcomes[actor_id, conversation_id] = replace(yes, actor_id=assessment.partner_id)
    elif source == "assessment":
        other = feedback(UUID(int=101))
        store.assessments[actor_id, assessment.partner_id] = CurrentFeedback(other)
    elif source in {"interaction", "prompt_interaction"}:
        store.source = replace(
            store.source, conversation=replace(store.source.conversation, relationship_id=uuid4())
        )
    else:
        store.prompts[actor_id, conversation_id] = StudyPromptReceipt(
            uuid4(), conversation_id, assessment.partner_id, store.clock
        )
    with pytest.raises(RuntimeError, match=r"source|interaction|participant|partner pair"):
        await invalid_source_operation(store, source)


async def invalid_source_operation(store: Store, source: str) -> None:
    if source == "outcome":
        await SaveStudyOutcome(store, HASHER, FP)(command(store, version=1))
    elif source in {"assessment", "interaction"}:
        await SaveFeedback(store, HASHER, FP)(review(store, version=1))
    else:
        await OfferStudyPromptOnVisit(store, HASHER, FP)(visit(store))


@pytest.mark.parametrize("source", ["outcome", "feedback"])
async def test_own_read_does_not_leak_foreign_retained_source(source: str) -> None:
    store = Store()
    yes = await SaveStudyOutcome(store, HASHER, FP)(command(store))
    assessment = await SaveFeedback(store, HASHER, FP)(review(store))
    actor_id = store.actor.session.account_id
    if source == "outcome":
        store.outcomes[actor_id, store.source.conversation.id] = replace(
            yes, actor_id=assessment.partner_id
        )
    else:
        store.assessments[actor_id, assessment.partner_id] = CurrentFeedback(
            feedback(UUID(int=101))
        )
    with pytest.raises(RuntimeError, match="projection belongs"):
        await read_foreign_source(store, source)


async def read_foreign_source(store: Store, source: str) -> None:
    if source == "outcome":
        await ReadOwnStudyOutcome(store, HASHER)(CREDENTIAL, store.source.conversation.id)
    else:
        await ReadOwnFeedback(store, HASHER)(CREDENTIAL, store.source.conversation.id)
