"""Real recipient/pending scoping, live declarations and no read-side mutations."""

from uuid import uuid4

import pytest
from sqlalchemy import event, func, select, update
from sqlalchemy.engine import Connection, ExecutionContext
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.application.idempotency import IntentKey
from studymate.application.profiles.goals import ReadOwnGoal, SaveGoalCommand, SaveOwnGoal
from studymate.application.profiles.help_subjects import (
    ReadOwnHelpSubjects,
    SaveHelpCommand,
    SaveOwnHelpSubjects,
)
from studymate.application.requests.response_options import ReadRequestResponseOptions
from studymate.application.requests.response_options_data import (
    LearningTooResponseOption,
    SwapResponseOption,
)
from studymate.domain.requests.states import RequestUnavailableError
from studymate.domain.study_context import HelpSubjects
from studymate.infrastructure.persistence.goals import SqlGoalUnitOfWork
from studymate.infrastructure.persistence.help_subjects import SqlHelpUnitOfWork
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.requests.response_options import SqlResponseOptionsUnitOfWork
from studymate.infrastructure.requests.view_models import (
    RequestDisclosureRecord,
    RequestViewAcknowledgementRecord,
)
from tests.integration.profile_lifecycle_fixture import command as visibility_command
from tests.integration.profile_lifecycle_fixture import services as visibility_services
from tests.integration.requests.fixture import (
    FINGERPRINTER,
    HASHER,
    action,
    additional_peer,
    prepared,
    sent,
)
from tests.integration.test_blocks import command as block_command
from tests.integration.test_blocks import reverse_context
from tests.integration.test_blocks import service as block_service

pytestmark = pytest.mark.integration


async def test_actual_current_references_and_read_produces_no_ack_activity_or_canonical_write(
    identity_engine: AsyncEngine,
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    value = await sent(api, sender, recipient)
    goal = await ReadOwnGoal(SqlGoalUnitOfWork(api.sessions), HASHER)(recipient.credential)
    help_source = await ReadOwnHelpSubjects(SqlHelpUnitOfWork(api.sessions), HASHER)(
        sender.credential
    )
    assert goal is not None
    assert help_source is not None
    mutations: list[str] = []

    def inspect(
        _connection: Connection,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: ExecutionContext,
        _executemany: bool,
    ) -> None:
        verb = statement.split(maxsplit=1)[0].upper()
        if verb in {"INSERT", "UPDATE", "DELETE"}:
            mutations.append(verb)

    event.listen(identity_engine.sync_engine, "before_cursor_execute", inspect)
    try:
        result = await ReadRequestResponseOptions(
            SqlResponseOptionsUnitOfWork(api.sessions), HASHER
        )(recipient.credential, value.id)
    finally:
        event.remove(identity_engine.sync_engine, "before_cursor_execute", inspect)
    assert tuple(option.kind for option in result.options) == (
        "learning_too",
        "swap",
        "write_my_own",
    )
    learning, swap = result.options[:2]
    assert isinstance(learning, LearningTooResponseOption)
    assert isinstance(swap, SwapResponseOption)
    assert learning.own_goal.id == goal.goal.id
    assert learning.own_goal.version == goal.goal.version
    assert swap.peer_help.account_id == sender.id
    assert swap.peer_help.version == help_source.revision.version
    assert mutations == []
    async with api.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(RequestDisclosureRecord)) == 0
        assert (
            await session.scalar(select(func.count()).select_from(RequestViewAcknowledgementRecord))
            == 0
        )


async def test_changes_after_sent_snapshot_update_suggestions_without_fabricating_shared_learning(
    identity_engine: AsyncEngine,
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    value = await sent(api, sender, recipient)
    read = ReadRequestResponseOptions(SqlResponseOptionsUnitOfWork(api.sessions), HASHER)
    old = await read(recipient.credential, value.id)
    uow = SqlGoalUnitOfWork(api.sessions)
    current = await ReadOwnGoal(uow, HASHER)(recipient.credential)
    assert current is not None
    from dataclasses import replace

    changed = await SaveOwnGoal(uow, HASHER, FINGERPRINTER)(
        SaveGoalCommand(
            recipient.credential,
            replace(current.goal.content, topic="Own different topic", shared_learning=False),
            current.goal.id,
            current.goal.version,
            IntentKey(str(uuid4())),
        )
    )
    help_uow = SqlHelpUnitOfWork(api.sessions)
    peer_help = await ReadOwnHelpSubjects(help_uow, HASHER)(sender.credential)
    assert peer_help is not None
    await SaveOwnHelpSubjects(help_uow, HASHER, FINGERPRINTER)(
        SaveHelpCommand(
            sender.credential, HelpSubjects(), peer_help.revision.version, IntentKey(str(uuid4()))
        )
    )
    fresh = await read(recipient.credential, value.id)
    assert fresh.request_version == old.request_version
    assert tuple(option.kind for option in fresh.options) == ("learning_too", "write_my_own")
    assert isinstance(fresh.options[0], LearningTooResponseOption)
    assert fresh.options[0].own_goal.version == changed.goal.version
    assert fresh.options[0].own_goal.topic == "Own different topic"
    assert "Own different topic" not in fresh.options[0].suggested_text
    assert "Synthetic topic" not in fresh.options[0].suggested_text


async def test_sender_and_foreign_actor_rejected_before_any_private_profile_or_preview_join(
    identity_engine: AsyncEngine,
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    value = await sent(api, sender, recipient)
    foreign = await additional_peer(identity_engine, value.context.subject_id)
    private_queries: list[str] = []

    def inspect(
        _connection: Connection,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: ExecutionContext,
        _executemany: bool,
    ) -> None:
        if "JOIN request_previews" in statement or "JOIN profile_revisions" in statement:
            private_queries.append("private_source")

    event.listen(identity_engine.sync_engine, "before_cursor_execute", inspect)
    try:
        for denied in (sender, foreign):
            with pytest.raises(RequestUnavailableError):
                await ReadRequestResponseOptions(
                    SqlResponseOptionsUnitOfWork(api.sessions), HASHER
                )(denied.credential, value.id)
    finally:
        event.remove(identity_engine.sync_engine, "before_cursor_execute", inspect)
    assert private_queries == []


async def test_pending_decline_has_no_response_options(identity_engine: AsyncEngine) -> None:
    sender, recipient, api = await prepared(identity_engine)
    value = await sent(api, sender, recipient)
    await api.decline(action(recipient, sender, value))
    with pytest.raises(RequestUnavailableError):
        await ReadRequestResponseOptions(SqlResponseOptionsUnitOfWork(api.sessions), HASHER)(
            recipient.credential, value.id
        )


@pytest.mark.parametrize("reason", ["hidden", "banned", "deleted", "blocked"])
async def test_current_contact_guard_dominates_retained_snapshot(
    identity_engine: AsyncEngine, reason: str
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    value = await sent(api, sender, recipient)
    if reason == "hidden":
        change, _ = visibility_services(identity_engine)
        await change(visibility_command(sender))
    elif reason == "blocked":
        source = await reverse_context(identity_engine, recipient, sender)
        await block_service(identity_engine)(block_command(recipient, sender, source))
    else:
        async with api.sessions.begin() as session:
            statement = update(AccountRecord).where(AccountRecord.id == sender.id)
            await session.execute(
                statement.values(banned_at=func.clock_timestamp())
                if reason == "banned"
                else statement.values(deleted_at=func.clock_timestamp())
            )
    with pytest.raises(RequestUnavailableError):
        await ReadRequestResponseOptions(SqlResponseOptionsUnitOfWork(api.sessions), HASHER)(
            recipient.credential, value.id
        )
