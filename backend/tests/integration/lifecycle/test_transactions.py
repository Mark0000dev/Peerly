"""Actual migrated PG transaction proof with controlled effects, not shared-effects acceptance."""

import asyncio
from dataclasses import replace
from datetime import datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.lifecycle.bans import ChangeAccountBan
from studymate.application.lifecycle.commands import ChangeAccountBanCommand
from studymate.application.lifecycle.intents import LifecycleResult
from studymate.domain.lifecycle.states import LifecycleReason
from studymate.infrastructure.lifecycle.ban_transactions import SqlBanUnitOfWork
from studymate.infrastructure.lifecycle.models import LifecycleIntentRecord, LifecycleRevisionRecord
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.product_events import record_operator_audit
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.integration.operator.test_reads import operator
from tests.integration.student_actor import actor

pytestmark = pytest.mark.integration
NOOP_AND_LATER_BAN = 2


async def controlled_effect(session: AsyncSession, transition: LifecycleResult) -> None:
    # Prove the callback sees the actual source within the same transaction.
    assert transition.revision is not None
    assert await session.get(LifecycleRevisionRecord, transition.revision.id) is not None


async def failing_effect(session: AsyncSession, transition: LifecycleResult) -> None:
    await controlled_effect(session, transition)
    raise RuntimeError("synthetic effect failure")


def usecase(engine: AsyncEngine) -> ChangeAccountBan:
    return ChangeAccountBan(
        SqlBanUnitOfWork(
            async_sessionmaker(engine, expire_on_commit=False),
            controlled_effect,
            record_operator_audit,
        ),
        Sha256SessionHasher(),
        HmacIntentFingerprinter(b"t" * 32),
    )


async def test_concurrent_same_intent_commits_one_original_source(
    identity_engine: AsyncEngine,
) -> None:
    owner, target = await operator(identity_engine), await actor(identity_engine)
    command = ChangeAccountBanCommand(
        owner.credential,
        target.id,
        True,
        LifecycleReason("  private exact reason  "),
        IntentKey("same-intent"),
    )
    first, second = await asyncio.gather(
        usecase(identity_engine)(command), usecase(identity_engine)(command)
    )
    assert first == second
    assert first.changed
    with pytest.raises(IdempotencyConflictError):
        await usecase(identity_engine)(replace(command, reason=LifecycleReason("changed")))
    async with async_sessionmaker(identity_engine)() as session:
        assert await session.scalar(select(func.count()).select_from(LifecycleRevisionRecord)) == 1
        assert await session.scalar(select(func.count()).select_from(LifecycleIntentRecord)) == 1
        source = (await session.scalars(select(LifecycleRevisionRecord))).one()
        assert source.reason == "  private exact reason  "
        assert source.http_request_id is None


async def test_effect_failure_rolls_back_pointer_source_and_intent(
    identity_engine: AsyncEngine,
) -> None:
    owner, target = await operator(identity_engine), await actor(identity_engine)
    command = ChangeAccountBanCommand(
        owner.credential,
        target.id,
        True,
        LifecycleReason("private reason"),
        IntentKey("rollback-intent"),
    )
    failing = ChangeAccountBan(
        SqlBanUnitOfWork(
            async_sessionmaker(identity_engine, expire_on_commit=False),
            failing_effect,
            record_operator_audit,
        ),
        Sha256SessionHasher(),
        HmacIntentFingerprinter(b"t" * 32),
    )
    with pytest.raises(RuntimeError, match="synthetic effect failure"):
        await failing(command)
    async with async_sessionmaker(identity_engine)() as session:
        account = await session.get(AccountRecord, target.id)
        assert account is not None
        assert account.banned_at is None
        assert account.lifecycle_version is None
        assert await session.scalar(select(func.count()).select_from(LifecycleRevisionRecord)) == 0
        assert await session.scalar(select(func.count()).select_from(LifecycleIntentRecord)) == 0
    assert (await usecase(identity_engine)(command)).changed


async def test_legacy_unban_noop_replay_keeps_original_snapshot(
    identity_engine: AsyncEngine,
) -> None:
    owner, target = await operator(identity_engine), await actor(identity_engine)
    command = ChangeAccountBanCommand(
        owner.credential,
        target.id,
        False,
        LifecycleReason("already unbanned"),
        IntentKey("noop-intent"),
    )
    original = await usecase(identity_engine)(command)
    assert not original.changed
    assert original.after.source_version == 0
    await usecase(identity_engine)(replace(command, banned=True, intent_key=IntentKey("later-ban")))
    assert await usecase(identity_engine)(command) == original
    async with async_sessionmaker(identity_engine)() as session:
        account = await session.get(AccountRecord, target.id)
        assert account is not None
        assert isinstance(account.banned_at, datetime)
        assert account.lifecycle_version == 1
        assert (
            await session.scalar(select(func.count()).select_from(LifecycleIntentRecord))
            == NOOP_AND_LATER_BAN
        )


async def test_ban_adapter_rejects_cross_scope_reads_and_writes(
    identity_engine: AsyncEngine,
) -> None:
    from studymate.application.lifecycle.intents import LifecycleIntent
    from studymate.application.operator.authority import require_operator
    from studymate.domain.lifecycle.states import BanTransition, LifecycleOperation

    owner, target = await operator(identity_engine), await actor(identity_engine)
    hasher = Sha256SessionHasher()
    uow = usecase(identity_engine).unit_of_work
    async with uow.transaction(await hasher.digest(owner.credential), target.id) as tx:
        with pytest.raises(RuntimeError):
            await tx.target_lifecycle(target.id)
        principal = await require_operator(tx, owner.credential, hasher)
        with pytest.raises(RuntimeError, match="lock scope"):
            await tx.target_lifecycle(owner.id)
        with pytest.raises(RuntimeError, match="actor/operation"):
            await tx.prior_lifecycle_intent(
                target.id, LifecycleOperation.BAN, IntentKey("wrong-actor")
            )
        state = await tx.target_lifecycle(target.id)
        assert state is not None
        noop = BanTransition(state, state, None)
        with pytest.raises(RuntimeError, match="authority"):
            await tx.apply_ban_transition(noop)
        with pytest.raises(RuntimeError, match="actor/target"):
            await tx.remember_lifecycle_intent(
                LifecycleIntent(
                    target.id, LifecycleOperation.UNBAN, IntentKey("wrong-owner"), b"x" * 32, noop
                ),
                await tx.now(),
            )
        assert principal.identity.session.account_id == owner.id
