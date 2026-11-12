"""Real human decisions, retained source proofs and independent student capabilities."""

import asyncio
import hashlib
from dataclasses import replace
from http import HTTPStatus
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.sessions import StudentActionDeniedError
from studymate.application.media.uploads import PhotoUploadCommand, StartPhotoCommand, UploadAction
from studymate.application.media.worker import PhotoProcessingStep
from studymate.application.operator.photo_review import (
    PhotoReviewVersionConflictError,
    ReviewPhoto,
    ReviewPhotoCommand,
)
from studymate.application.profiles.photo_review import ReadOwnPhotoReview
from studymate.domain.media import PhotoContentType, PhotoSource
from studymate.domain.operator.photo_review import (
    PhotoRecoveryState,
    PhotoReviewAction,
    PhotoReviewRevision,
)
from studymate.infrastructure.media.images import BoundedImageProcessor
from studymate.infrastructure.operator.photo_review_models import (
    OperatorPhotoReviewIntentRecord,
    OperatorPhotoReviewRecord,
)
from studymate.infrastructure.operator.photo_review_owner import SqlOwnPhotoReviewUnitOfWork
from studymate.infrastructure.operator.photo_review_transactions import SqlPhotoReviewUnitOfWork
from studymate.infrastructure.persistence.onboarding import read_setup_snapshot
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import (
    record_operator_audit,
    record_photo_review_event,
)
from studymate.presentation.browser import SESSION_COOKIE
from tests.image_fixture import encoded
from tests.integration.http_identity import BrowserHarness, write_headers
from tests.integration.media_fixture import Storage, services, worker
from tests.integration.operator.test_reads import operator
from tests.integration.operator.test_reports import reports
from tests.integration.profile_lifecycle_fixture import activated
from tests.integration.profile_lifecycle_fixture import services as profile_services
from tests.integration.requests.fixture import FINGERPRINTER, HASHER, action, prepared, sent
from tests.integration.student_actor import Actor
from tests.integration.test_message_commands import chat

pytestmark = pytest.mark.integration


def reviewer(engine: AsyncEngine) -> ReviewPhoto:
    return ReviewPhoto(
        SqlPhotoReviewUnitOfWork(
            async_sessionmaker(engine, expire_on_commit=False),
            record_operator_audit,
            record_photo_review_event,
        ),
        HASHER,
        FINGERPRINTER,
    )


async def request_replacement(
    engine: AsyncEngine, moderator: Actor, target: Actor
) -> PhotoReviewRevision:
    async with async_sessionmaker(engine)() as session:
        photo = (await read_setup_snapshot(session, target.id)).photo
    assert photo is not None
    return await reviewer(engine)(
        ReviewPhotoCommand(
            moderator.credential,
            target.id,
            0,
            photo.version,
            photo.upload_id,
            PhotoReviewAction.REQUIRE_REPLACEMENT,
            "Private moderation reason",
            IntentKey(str(uuid4())),
        )
    )


async def test_real_requirement_new_upload_and_explicit_approval_do_not_create_global_gate(
    identity_engine: AsyncEngine,
) -> None:
    target, moderator = await activated(identity_engine), await operator(identity_engine)
    _, status = profile_services(identity_engine)
    assert (await status(target.credential)).capabilities.can_discover
    required = await request_replacement(identity_engine, moderator, target)
    restricted = (await status(target.credential)).capabilities
    assert not restricted.can_discover
    assert restricted.can_access_existing_chats
    assert restricted.can_manage_profile
    own = ReadOwnPhotoReview(
        SqlOwnPhotoReviewUnitOfWork(async_sessionmaker(identity_engine, expire_on_commit=False)),
        HASHER,
    )
    assert (await own(target.credential)).state == PhotoRecoveryState.REPLACEMENT_REQUIRED
    data = encoded()
    start, change, _ = services(identity_engine)
    upload = await start(
        StartPhotoCommand(
            target.credential,
            PhotoSource(len(data), hashlib.sha256(data).digest(), PhotoContentType.PNG),
            required.photo.version,
            IntentKey(str(uuid4())),
        )
    )
    await change(
        PhotoUploadCommand(
            target.credential, upload.id, UploadAction.FINALIZE, IntentKey(str(uuid4()))
        )
    )
    processor = BoundedImageProcessor()
    try:
        assert (
            await worker(identity_engine, Storage(data), processor)() == PhotoProcessingStep.READY
        )
    finally:
        await processor.close()
    assert (await own(target.credential)).state == PhotoRecoveryState.AWAITING_HUMAN_REVIEW
    assert not (await status(target.credential)).capabilities.can_discover
    async with async_sessionmaker(identity_engine)() as session:
        current = (await read_setup_snapshot(session, target.id)).photo
    assert current is not None
    approved = await reviewer(identity_engine)(
        ReviewPhotoCommand(
            moderator.credential,
            target.id,
            1,
            current.version,
            current.upload_id,
            PhotoReviewAction.APPROVE_REPLACEMENT,
            "New photo reviewed by human",
            IntentKey(str(uuid4())),
        )
    )
    assert approved.version == required.version + 1
    assert (await own(target.credential)).state == PhotoRecoveryState.NOT_REQUIRED
    assert (await status(target.credential)).capabilities.can_discover
    async with async_sessionmaker(identity_engine)() as session:
        assert (
            await session.scalar(select(func.count()).select_from(OperatorPhotoReviewRecord))
            == approved.version
        )


async def test_same_source_race_commits_one_version_without_discarding_operator_proof(
    identity_engine: AsyncEngine,
) -> None:
    target = await activated(identity_engine)
    first, second = await operator(identity_engine), await operator(identity_engine)
    results = await asyncio.gather(
        request_replacement(identity_engine, first, target),
        request_replacement(identity_engine, second, target),
        return_exceptions=True,
    )
    assert sum(isinstance(result, PhotoReviewRevision) for result in results) == 1
    assert sum(isinstance(result, PhotoReviewVersionConflictError) for result in results) == 1
    async with async_sessionmaker(identity_engine)() as session:
        source = (await session.scalars(select(OperatorPhotoReviewRecord))).one()
        event = await session.get(ProductEventRecord, source.id)
        assert event is not None
        assert event.account_id == source.operator_id
        assert event.photo_review_id == source.id
        assert event.photo_review_version == source.version
        assert event.occurred_at == source.decided_at
        assert event.report_id is None


async def test_canonical_failure_rolls_back_human_source_and_actor_intent(
    identity_engine: AsyncEngine,
) -> None:
    target, moderator = await activated(identity_engine), await operator(identity_engine)
    async with async_sessionmaker(identity_engine)() as session:
        photo = (await read_setup_snapshot(session, target.id)).photo
    assert photo is not None
    command = ReviewPhotoCommand(
        moderator.credential,
        target.id,
        0,
        photo.version,
        photo.upload_id,
        PhotoReviewAction.REQUIRE_REPLACEMENT,
        "Private reason",
        IntentKey(str(uuid4())),
    )

    async def fail(session: AsyncSession, source: PhotoReviewRevision) -> None:
        await record_photo_review_event(session, source)
        raise RuntimeError("Synthetic canonical failure")

    broken = ReviewPhoto(
        SqlPhotoReviewUnitOfWork(
            async_sessionmaker(identity_engine, expire_on_commit=False), record_operator_audit, fail
        ),
        HASHER,
        FINGERPRINTER,
    )
    with pytest.raises(RuntimeError, match="Synthetic canonical failure"):
        await broken(command)
    async with async_sessionmaker(identity_engine)() as session:
        assert (
            await session.scalar(select(func.count()).select_from(OperatorPhotoReviewRecord)) == 0
        )
        assert (
            await session.scalar(select(func.count()).select_from(OperatorPhotoReviewIntentRecord))
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProductEventRecord)
                .where(ProductEventRecord.kind == "photo.reviewed")
            )
            == 0
        )
    success = await reviewer(identity_engine)(command)
    assert await reviewer(identity_engine)(command) == success
    with pytest.raises(IdempotencyConflictError):
        await reviewer(identity_engine)(replace(command, expected_version=success.version))


async def test_replacement_requirement_never_freezes_existing_conversation(
    identity_engine: AsyncEngine,
) -> None:
    owned, moderator = await chat(identity_engine), await operator(identity_engine)
    await request_replacement(identity_engine, moderator, owned.sender)
    sent = await owned.send()(owned.command())
    assert sent.message is not None
    assert sent.message.author_id == owned.sender.id


async def test_root_photo_review_is_privileged_and_owner_receives_only_recovery_state(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
) -> None:
    target, moderator = await activated(identity_engine), await operator(identity_engine)
    browser.client.cookies.set(SESSION_COOKIE, moderator.credential.value)
    path = f"/api/v1/operator/accounts/{target.id}"
    context = await browser.client.get(path + "/photo-review")
    assert context.status_code == HTTPStatus.OK
    photo = context.json()["current_photo"]
    payload = {
        "expected_version": 0,
        "expected_photo_version": photo["version"],
        "expected_upload_id": photo["upload_id"],
        "action": "require_replacement",
        "reason": "PRIVATE_PHOTO_REASON_CANARY",
    }
    invalid = await browser.client.post(
        path + "/photo-reviews",
        json={**payload, "reason": "   "},
        headers=await write_headers(browser.client),
    )
    assert invalid.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    created = await browser.client.post(
        path + "/photo-reviews", json=payload, headers=await write_headers(browser.client)
    )
    assert created.status_code == HTTPStatus.OK
    assert created.json()["version"] == 1
    browser.client.cookies.set(SESSION_COOKIE, target.credential.value)
    recovery = await browser.client.get("/api/v1/me/photo-review")
    assert recovery.status_code == HTTPStatus.OK
    assert recovery.json() == {"version": 1, "state": "replacement_required"}
    assert "PRIVATE_PHOTO_REASON_CANARY" not in recovery.text
    assert str(moderator.id) not in recovery.text
    assert (await browser.client.get(path + "/photo-review")).status_code == HTTPStatus.FORBIDDEN


async def test_photo_requirement_retains_pending_request_and_decline_without_accept(
    identity_engine: AsyncEngine,
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    request = await sent(api, sender, recipient)
    moderator = await operator(identity_engine)
    await request_replacement(identity_engine, moderator, recipient)
    with pytest.raises(StudentActionDeniedError):
        await api.accept(action(recipient, sender, request))
    declined = await api.decline(action(recipient, sender, request))
    assert declined.id == request.id
    assert declined.state.value == "pending_decline"


async def test_root_report_review_preserves_reporter_ownership_and_canonical_drilldown(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
) -> None:
    scenario = await reports(identity_engine)
    browser.client.cookies.set(SESSION_COOKIE, scenario.owner.credential.value)
    path = f"/api/v1/operator/reports/{scenario.report.id}/reviews"
    before = await browser.client.get(path)
    assert before.status_code == HTTPStatus.OK
    assert before.json()["current"] is None
    result = await browser.client.post(
        path,
        json={"expected_version": 0, "action": "dismiss", "reason": "Private root review"},
        headers=await write_headers(browser.client),
    )
    assert result.status_code == HTTPStatus.OK
    event = await browser.client.get(f"/api/v1/operator/events/{result.json()['event_id']}")
    assert event.status_code == HTTPStatus.OK
    assert event.json()["kind"] == "report.reviewed"
    async with scenario.uow.sessions() as session:
        retained = await session.get(ProductEventRecord, UUID(result.json()["event_id"]))
        assert retained is not None
        assert retained.account_id == scenario.owner.id
        assert retained.report_id is None
        assert retained.report_review_report_id == scenario.report.id
