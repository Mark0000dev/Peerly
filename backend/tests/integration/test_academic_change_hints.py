import hashlib
from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.application.changes.reads import ReadChanges
from studymate.application.discovery.profiles import ReadDiscoveryProfile
from studymate.application.idempotency import IntentKey
from studymate.application.media.uploads import PhotoUploadCommand, StartPhotoCommand, UploadAction
from studymate.application.media.worker import PhotoProcessingStep
from studymate.application.profiles.basics import SaveProfileCommand
from studymate.application.safety.blocks import ChangeBlockCommand, ChangeOwnBlock
from studymate.domain.changes import ChangeResource
from studymate.domain.media import PhotoContentType, PhotoSource
from studymate.domain.profiles import DisplayName, ProfileRevision
from studymate.infrastructure.changes.models import ChangeOutboxRecord, PublishedChangeRecord
from studymate.infrastructure.changes.reads import SqlChangeReadUnitOfWork
from studymate.infrastructure.media.images import BoundedImageProcessor
from studymate.infrastructure.persistence.blocks import SqlBlockUnitOfWork
from studymate.infrastructure.persistence.discovery_profiles import SqlDiscoveryProfileUnitOfWork
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    InstitutionalBindingRecord,
)
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.presentation.changes.frames import change_frame
from tests.image_fixture import encoded
from tests.integration.change_fixture import drain, head_positions
from tests.integration.media_fixture import Storage, worker
from tests.integration.media_fixture import services as media_services
from tests.integration.profile_lifecycle_fixture import command as hide_command
from tests.integration.profile_lifecycle_fixture import services as visibility_services
from tests.integration.requests.fixture import FINGERPRINTER, HASHER
from tests.integration.test_message_commands import Chat, chat
from tests.integration.test_profiles import services as profile_services

pytestmark = pytest.mark.integration


async def change_profile(
    engine: AsyncEngine, owned: Chat, *, rename: bool = True
) -> ProfileRevision:
    save, read = profile_services(engine)
    profile = (await read(owned.sender.credential)).profile
    assert profile is not None
    basics = (
        replace(profile.basics, display_name=DisplayName("Changed synthetic name"))
        if rename
        else replace(profile.basics, about="Private changed about")
    )
    return await save(
        SaveProfileCommand(
            owned.sender.credential, basics, profile.task, profile.version, IntentKey(str(uuid4()))
        )
    )


async def profile_event(owned: Chat, profile: ProfileRevision) -> ProductEventRecord:
    async with owned.api.sessions() as session:
        return (
            await session.scalars(
                select(ProductEventRecord).where(
                    ProductEventRecord.account_id == owned.sender.id,
                    ProductEventRecord.kind == "profile.saved",
                    ProductEventRecord.profile_version == profile.version,
                )
            )
        ).one()


async def recipients(owned: Chat, event: ProductEventRecord) -> frozenset[UUID]:
    async with owned.api.sessions() as session:
        return frozenset(
            await session.scalars(
                select(ChangeOutboxRecord.recipient_id).where(
                    ChangeOutboxRecord.canonical_event_id == event.id
                )
            )
        )


async def block(owned: Chat, *, reverse: bool = False) -> None:
    actor, target = (owned.recipient, owned.sender) if reverse else (owned.sender, owned.recipient)
    context = await ReadDiscoveryProfile(SqlDiscoveryProfileUnitOfWork(owned.api.sessions), HASHER)(
        actor.credential, target.id
    )
    await ChangeOwnBlock(SqlBlockUnitOfWork(owned.api.sessions), HASHER, FINGERPRINTER)(
        ChangeBlockCommand(
            actor.credential, target.id, True, 0, IntentKey(str(uuid4())), context.access_context.id
        )
    )


@pytest.mark.parametrize("hidden", ["actor", "recipient", "both"])
async def test_name_change_invalidates_hidden_accepted_contacts_without_private_profile_grant(
    identity_engine: AsyncEngine,
    hidden: str,
) -> None:
    owned = await chat(identity_engine)
    hide, _ = visibility_services(identity_engine)
    for actor in (owned.sender, owned.recipient):
        if hidden == "both" or (hidden == "actor") == (actor.id == owned.sender.id):
            await hide(hide_command(actor))
    await drain(owned)
    before = (await head_positions(owned))[owned.recipient.id]
    profile = await change_profile(identity_engine, owned)
    event = await profile_event(owned, profile)
    assert await recipients(owned, event) == frozenset({owned.sender.id, owned.recipient.id})
    await drain(owned)
    page = await ReadChanges(SqlChangeReadUnitOfWork(owned.api.sessions), HASHER)(
        owned.recipient.credential, before
    )
    own = tuple(item for item in page.changes if item.hint.canonical_event_id == event.id)
    assert len(own) == 1
    assert own[0].hint.resource_type == ChangeResource.ACCOUNT
    assert own[0].hint.resource_id == owned.recipient.id
    assert own[0].hint.version is None
    frame = change_frame(own[0])
    assert b"Changed synthetic name" not in frame
    assert str(owned.sender.id).encode() not in frame


async def test_about_only_change_does_not_signal_peer_profile_activity(
    identity_engine: AsyncEngine,
) -> None:
    owned = await chat(identity_engine)
    event = await profile_event(owned, await change_profile(identity_engine, owned, rename=False))
    assert await recipients(owned, event) == frozenset({owned.sender.id})


@pytest.mark.parametrize("reverse", [False, True], ids=["outbound-block", "inbound-block"])
async def test_blocked_contact_is_not_staged_for_new_profile_activity(
    identity_engine: AsyncEngine,
    reverse: bool,
) -> None:
    owned = await chat(identity_engine)
    await block(owned, reverse=reverse)
    event = await profile_event(owned, await change_profile(identity_engine, owned))
    assert await recipients(owned, event) == frozenset({owned.sender.id})


async def test_block_after_staging_does_not_destroy_retained_delivery_source(
    identity_engine: AsyncEngine,
) -> None:
    owned = await chat(identity_engine)
    await drain(owned)
    before = (await head_positions(owned))[owned.recipient.id]
    event = await profile_event(owned, await change_profile(identity_engine, owned))
    # Capture valid stage eligibility, then change current contact authority before publication.
    await block(owned)
    await drain(owned)
    page = await ReadChanges(SqlChangeReadUnitOfWork(owned.api.sessions), HASHER)(
        owned.recipient.credential, before
    )
    assert any(item.hint.canonical_event_id == event.id for item in page.changes)
    assert await recipients(owned, event) == frozenset({owned.sender.id, owned.recipient.id})


async def test_later_connection_cannot_retroactively_add_profile_event_recipient(
    identity_engine: AsyncEngine,
) -> None:
    owned = await chat(identity_engine)
    async with owned.api.sessions() as session:
        initial = (
            await session.scalars(
                select(ProductEventRecord).where(
                    ProductEventRecord.kind == "profile.saved",
                    ProductEventRecord.account_id == owned.sender.id,
                    ProductEventRecord.profile_version == 1,
                )
            )
        ).one()
    assert await recipients(owned, initial) == frozenset({owned.sender.id})
    # The accepted relationship now exists; publication may not expand the frozen outbox.
    await drain(owned)
    async with owned.api.sessions() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(PublishedChangeRecord)
                .where(
                    PublishedChangeRecord.canonical_event_id == initial.id,
                    PublishedChangeRecord.recipient_id == owned.recipient.id,
                )
            )
            == 0
        )


@pytest.mark.parametrize("lifecycle", ["banned", "deleted", "unverified"])
async def test_unavailable_receiver_has_no_new_contact_invalidation(
    identity_engine: AsyncEngine,
    lifecycle: str,
) -> None:
    owned = await chat(identity_engine)
    async with owned.api.sessions.begin() as session:
        if lifecycle == "unverified":
            await session.execute(
                update(InstitutionalBindingRecord)
                .where(InstitutionalBindingRecord.account_id == owned.recipient.id)
                .values(revoked_at=func.clock_timestamp())
            )
        else:
            await session.execute(
                update(AccountRecord)
                .where(AccountRecord.id == owned.recipient.id)
                .values(
                    **{
                        "banned_at"
                        if lifecycle == "banned"
                        else "deleted_at": func.clock_timestamp()
                    }
                )
            )
    event = await profile_event(owned, await change_profile(identity_engine, owned))
    assert await recipients(owned, event) == frozenset({owned.sender.id})


async def test_actual_photo_replacement_invalidates_current_chat_avatar_without_publishing_bytes(
    identity_engine: AsyncEngine,
) -> None:
    owned = await chat(identity_engine)
    snapshot = await profile_services(identity_engine)[1](owned.sender.credential)
    assert snapshot.photo is not None
    data = encoded()
    begin, finalize, _ = media_services(identity_engine)
    upload = await begin(
        StartPhotoCommand(
            owned.sender.credential,
            PhotoSource(len(data), hashlib.sha256(data).digest(), PhotoContentType.PNG),
            snapshot.photo.version,
            IntentKey(str(uuid4())),
        )
    )
    await finalize(
        PhotoUploadCommand(
            owned.sender.credential, upload.id, UploadAction.FINALIZE, IntentKey(str(uuid4()))
        )
    )
    processor = BoundedImageProcessor()
    try:
        assert (
            await worker(identity_engine, Storage(data), processor)() == PhotoProcessingStep.READY
        )
    finally:
        await processor.close()
    async with owned.api.sessions() as session:
        event = (
            await session.scalars(
                select(ProductEventRecord).where(
                    ProductEventRecord.kind == "photo.published",
                    ProductEventRecord.account_id == owned.sender.id,
                    ProductEventRecord.photo_version == snapshot.photo.version + 1,
                )
            )
        ).one()
    assert await recipients(owned, event) == frozenset({owned.sender.id, owned.recipient.id})
