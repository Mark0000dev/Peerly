from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest

from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.sessions import StudentActionDeniedError, UnauthenticatedError
from studymate.application.safety.message_reports import (
    IssueMessageImageReportContext,
    SubmitMessageImageReport,
    SubmitMessageImageReportCommand,
)
from studymate.application.safety.profile_reports import (
    ProfileReportRateLimitedError,
    ReportContextUnavailableError,
)
from studymate.domain.message_reports import MessageImageRef, MessageImageReportContext
from studymate.domain.reports import ReportCategory
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.unit.identity_store import CREDENTIAL, NOW
from tests.unit.safety.message_reports.store import Store


async def context(store: Store) -> MessageImageReportContext:
    assert store.source is not None
    return await IssueMessageImageReportContext(store, Sha256SessionHasher())(
        CREDENTIAL, store.source.conversation_id, store.source.message_id
    )


def submit(store: Store) -> SubmitMessageImageReport:
    return SubmitMessageImageReport(
        store, Sha256SessionHasher(), HmacIntentFingerprinter(b"r" * 32)
    )


async def command(store: Store) -> SubmitMessageImageReportCommand:
    issued = await context(store)
    return SubmitMessageImageReportCommand(
        CREDENTIAL,
        issued.id,
        ReportCategory.HARASSMENT,
        IntentKey("message-report-key"),
        "Private report comment",
    )


async def test_actual_context_replay_does_not_repeat_report_or_quota() -> None:
    store = Store()
    intent = await command(store)
    first = await submit(store)(intent)
    assert first.context == store.contexts[intent.context_id]
    assert await submit(store)(intent) == first
    assert len(store.reports) == 1
    assert store.events == [first.id]
    assert store.budget_reads == 1
    assert "Private report comment" not in repr(first)
    assert "Private report comment" not in repr(intent)
    with pytest.raises(IdempotencyConflictError):
        await submit(store)(replace(intent, comment="Changed private payload"))
    assert len(store.reports) == 1


async def test_contact_restrictions_do_not_remove_message_report_authority() -> None:
    store = Store()
    assert store.access is not None
    store.access = replace(store.access, blocked=True, peer_banned=True, peer_deleted=True)
    intent = await command(store)
    assert (await submit(store)(intent)).reporter_id == store.actor.session.account_id


@pytest.mark.parametrize("fault", ["text", "missing", "own"])
async def test_only_actual_peer_confirmed_image_is_reportable(fault: str) -> None:
    store = Store()
    assert store.source is not None
    source = store.source
    if fault == "text":
        store.source = replace(source, image=None)
    elif fault == "missing":
        store.source = None
    else:
        store.source = replace(source, author_id=store.actor.session.account_id)
    with pytest.raises(ReportContextUnavailableError):
        await IssueMessageImageReportContext(store, Sha256SessionHasher())(
            CREDENTIAL, source.conversation_id, source.message_id
        )
    assert not store.contexts


@pytest.mark.parametrize("fault", ["ban", "deleted", "unverified", "activation"])
async def test_current_actor_guard_also_applies_to_committed_receipt_replay(fault: str) -> None:
    store = Store()
    intent = await command(store)
    await submit(store)(intent)
    if fault == "ban":
        store.actor = replace(store.actor, banned=True)
    elif fault == "deleted":
        store.actor = replace(store.actor, deleted_at=NOW)
    elif fault == "unverified":
        store.actor = replace(store.actor, membership=None)
    else:
        store.actor = replace(store.actor, activation_complete=False)
    error = UnauthenticatedError if fault == "deleted" else StudentActionDeniedError
    with pytest.raises(error):
        await submit(store)(intent)
    assert len(store.reports) == 1


async def test_profile_history_spends_the_same_report_hour_budget() -> None:
    store = Store()
    intent = await command(store)
    store.profile_submissions = (NOW - timedelta(minutes=1),) * 10
    with pytest.raises(ProfileReportRateLimitedError) as caught:
        await submit(store)(intent)
    assert caught.value.retry_at == NOW + timedelta(minutes=59)
    assert not store.reports
    assert not store.events
    assert not store.intents


async def test_original_message_image_fk_is_rechecked_at_submission() -> None:
    store = Store()
    intent = await command(store)
    assert store.source is not None
    store.source = replace(store.source, image=MessageImageRef(uuid4(), 1, uuid4()))
    with pytest.raises(ReportContextUnavailableError):
        await submit(store)(intent)
    assert not store.reports


async def test_no_unknown_or_foreign_context_grants_authority() -> None:
    store = Store()
    intent = await command(store)
    with pytest.raises(ReportContextUnavailableError):
        await submit(store)(replace(intent, context_id=uuid4()))
    stored = store.contexts[intent.context_id]
    store.contexts[intent.context_id] = replace(stored, id=uuid4())
    with pytest.raises(RuntimeError, match="retained owner"):
        await submit(store)(intent)


@pytest.mark.parametrize("failure", ["canonical", "deadline"])
async def test_report_source_canonical_and_intent_roll_back_together(failure: str) -> None:
    store = Store()
    intent = await command(store)
    store.failure_after_report = failure == "canonical"
    store.expire_after_intent = failure == "deadline"
    error = RuntimeError if failure == "canonical" else UnauthenticatedError
    with pytest.raises(error):
        await submit(store)(intent)
    assert not store.reports
    assert not store.events
    assert not store.intents
    assert intent.context_id in store.contexts


async def test_context_creation_expiry_rolls_back_issued_reference() -> None:
    store = Store()
    store.expire_after_context = True
    with pytest.raises(UnauthenticatedError):
        await context(store)
    assert not store.contexts


async def test_original_session_cannot_be_substituted_during_submission() -> None:
    store = Store()
    intent = await command(store)
    store.identity_reads = 0
    store.switch_session = True
    with pytest.raises(UnauthenticatedError):
        await submit(store)(intent)
    assert not store.reports


async def test_missing_retained_result_is_not_recreated_on_replay() -> None:
    store = Store()
    intent = await command(store)
    await submit(store)(intent)
    store.reports.clear()
    with pytest.raises(RuntimeError, match="exact original result"):
        await submit(store)(intent)
