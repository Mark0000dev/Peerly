"""Actual participant history grants, current actor guards and adapter scope rejection."""

from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.application.discovery.profiles import ReadDiscoveryProfile
from studymate.application.idempotency import IntentKey
from studymate.application.identity.sessions import (
    StudentActionDeniedError,
    UnauthenticatedError,
    require_verified_student,
)
from studymate.application.messaging.commands import authorize_conversation
from studymate.application.messaging.ports import ConversationUnavailableError
from studymate.application.safety.blocks import ChangeBlockCommand, ChangeOwnBlock
from studymate.application.safety.message_reports import IssueMessageImageReportContext
from studymate.application.safety.profile_reports import ReportContextUnavailableError
from studymate.domain.message_reports import MessageImageRef, MessageImageReport
from studymate.domain.reports import ReportCategory
from studymate.infrastructure.persistence.blocks import SqlBlockUnitOfWork
from studymate.infrastructure.persistence.discovery_profiles import SqlDiscoveryProfileUnitOfWork
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    InstitutionalBindingRecord,
    SessionRecord,
)
from tests.integration.lifecycle.test_deletion_transactions import command_for
from tests.integration.lifecycle.test_real_effects import deletion
from tests.integration.onboarding_fixture import ready_setup
from tests.integration.profile_lifecycle_fixture import complete_existing_setup
from tests.integration.requests.fixture import FINGERPRINTER, HASHER
from tests.integration.safety.message_reports.fixture import prepared
from tests.integration.student_actor import actor

pytestmark = pytest.mark.integration


async def test_context_requires_peer_actual_image_message_and_participant(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    issue = IssueMessageImageReportContext(api.uow, HASHER)
    source = api.context.source
    with pytest.raises(ReportContextUnavailableError):
        await issue(api.chat.sender.credential, source.conversation_id, source.message_id)
    assert source.image is not None
    with pytest.raises(ReportContextUnavailableError):
        await issue(api.chat.recipient.credential, source.conversation_id, source.image.id)
    text = await api.chat.send()(api.chat.command())
    assert text.message is not None
    with pytest.raises(ReportContextUnavailableError):
        await issue(api.chat.recipient.credential, source.conversation_id, text.message.id)
    outsider = await actor(identity_engine)
    await ready_setup(identity_engine, outsider.credential)
    await complete_existing_setup(identity_engine, outsider)
    with pytest.raises(ConversationUnavailableError):
        await issue(outsider.credential, source.conversation_id, source.message_id)
    with pytest.raises(ReportContextUnavailableError):
        await api.submit()(replace(api.command(), credential=outsider.credential))


async def test_block_and_deleted_peer_preserve_actual_image_report_context_and_submission(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    profile = await ReadDiscoveryProfile(
        SqlDiscoveryProfileUnitOfWork(api.chat.api.sessions), HASHER
    )(api.chat.recipient.credential, api.chat.sender.id)
    await ChangeOwnBlock(SqlBlockUnitOfWork(api.chat.api.sessions), HASHER, FINGERPRINTER)(
        ChangeBlockCommand(
            api.chat.recipient.credential,
            api.chat.sender.id,
            True,
            0,
            IntentKey("report-block-peer"),
            profile.access_context.id,
        )
    )
    await deletion(identity_engine)(await command_for(identity_engine, api.chat.sender))
    source = api.context.source
    issued = await IssueMessageImageReportContext(api.uow, HASHER)(
        api.chat.recipient.credential, source.conversation_id, source.message_id
    )
    assert issued.source == source
    report = await api.submit()(replace(api.command(), context_id=issued.id))
    assert report.context == issued
    assert await api.submit()(replace(api.command(), context_id=issued.id)) == report


@pytest.mark.parametrize("restriction", ["banned", "deleted", "revoked", "unverified"])
async def test_current_actor_restriction_denies_issue_and_committed_replay(
    identity_engine: AsyncEngine, restriction: str
) -> None:
    api = await prepared(identity_engine)
    await api.submit()(api.command())
    async with api.chat.api.sessions.begin() as session:
        actor_id = api.chat.recipient.id
        if restriction == "banned":
            await session.execute(
                update(AccountRecord)
                .where(AccountRecord.id == actor_id)
                .values(banned_at=func.clock_timestamp())
            )
        elif restriction == "deleted":
            await session.execute(
                update(AccountRecord)
                .where(AccountRecord.id == actor_id)
                .values(deleted_at=func.clock_timestamp())
            )
        elif restriction == "revoked":
            await session.execute(
                update(SessionRecord)
                .where(SessionRecord.account_id == actor_id)
                .values(revoked_at=func.clock_timestamp())
            )
        else:
            await session.execute(
                update(InstitutionalBindingRecord)
                .where(InstitutionalBindingRecord.account_id == actor_id)
                .values(revoked_at=func.clock_timestamp())
            )
    error = (
        StudentActionDeniedError
        if restriction in {"banned", "unverified"}
        else UnauthenticatedError
    )
    with pytest.raises(error):
        await api.submit()(api.command())
    with pytest.raises(error):
        await IssueMessageImageReportContext(api.uow, HASHER)(
            api.chat.recipient.credential,
            api.context.source.conversation_id,
            api.context.source.message_id,
        )


async def test_sql_ports_reject_forged_actor_conversation_and_context_sources(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    actor_id = api.chat.recipient.id
    digest = await HASHER.digest(api.chat.recipient.credential)
    source = api.context.source
    async with api.uow.for_message(source.conversation_id) as tx:
        with pytest.raises(RuntimeError, match="current actor"):
            await tx.message_source(actor_id, source.conversation_id, source.message_id)
        await require_verified_student(tx, digest)
        with pytest.raises(RuntimeError, match="accepted conversation"):
            await tx.message_source(actor_id, source.conversation_id, source.message_id)
        with pytest.raises(RuntimeError, match="resolved lock scope"):
            await tx.conversation(actor_id, uuid4())
        await authorize_conversation(
            tx, HASHER, api.chat.recipient.credential, source.conversation_id
        )
        with pytest.raises(RuntimeError, match="current actor"):
            await tx.report_intent(api.chat.sender.id, IntentKey("wrong-scope-key"))
        forged = replace(
            api.context,
            id=uuid4(),
            source=replace(source, image=MessageImageRef(uuid4(), 1, uuid4())),
        )
        with pytest.raises(RuntimeError, match="confirmed image evidence"):
            await tx.add_context(forged)
        unknown = replace(api.context, id=uuid4())
        report = MessageImageReport(uuid4(), actor_id, unknown, ReportCategory.SPAM, await tx.now())
        with pytest.raises(RuntimeError, match="retained owned image context"):
            await tx.add_message_report(report)
        assert await tx.own_message_report(actor_id, uuid4()) is None
    async with api.uow.for_message(uuid4()) as tx:
        await require_verified_student(tx, digest)
        with pytest.raises(RuntimeError, match="conversation lock scope"):
            await tx.owned_context(actor_id, api.context.id)
    async with api.uow.for_context(uuid4()) as tx:
        await require_verified_student(tx, digest)
        with pytest.raises(RuntimeError, match="resolved lock scope"):
            await tx.conversation(actor_id, source.conversation_id)
