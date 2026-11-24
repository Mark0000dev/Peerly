"""Bounded durable recipient queue; no provider IO while holding core locks."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import DateTime, and_, cast, event, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.errors import StorageUnavailableError
from studymate.domain.notification_preferences.state import NotificationMode
from studymate.domain.student_notifications.delivery import (
    Claim,
    Delivery,
    Kind,
    Outcome,
    State,
    completion,
)
from studymate.infrastructure.notification_preferences.models import PreferenceRevisionRecord
from studymate.infrastructure.observability.origin import ExecutionOrigin
from studymate.infrastructure.observability.student_notification_delivery import (
    record_authorized,
    record_completed,
)
from studymate.infrastructure.persistence.block_models import (
    BlockRecord,
    BlockRevisionRecord,
    RelationshipRecord,
)
from studymate.infrastructure.persistence.identity_claims import identity_lineage_banned
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    InstitutionalBindingRecord,
)
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.transactions import open_transaction
from studymate.infrastructure.student_notifications.models import ConsumerRecord, DeliveryRecord
from studymate.infrastructure.student_notifications.sources import target
from studymate.infrastructure.student_notifications.transaction_diagnostics import (
    Operation,
    Phase,
    Progress,
    Stage,
    report,
)

ACTIVE = (State.PENDING.value, State.CLAIMED.value, State.SENDING.value)
LEASE = timedelta(seconds=30)
TTL = timedelta(days=1)
SOURCE_BATCH = 50
PARTICIPANTS = 2
GLOBAL_PENDING = 1000
RECIPIENT_PENDING = 100


@asynccontextmanager
async def transaction(
    sessions: async_sessionmaker[AsyncSession],
    *,
    read_only: bool = False,
    progress: Progress | None = None,
) -> AsyncIterator[AsyncSession]:
    observation = progress if progress is not None else Progress()
    deadline = asyncio.timeout(2)
    tracked: AsyncSession | None = None
    try:
        async with deadline, open_transaction(sessions, read_only=read_only) as session:
            tracked = session
            observation.phase = Phase.BODY
            observation.stage = Stage.BODY
            observation.sample_pool(session)
            event.listen(session.sync_session, "after_begin", observation.began)
            try:
                yield session
                observation.phase = Phase.COMMIT
                observation.stage = Stage.EXIT
                observation.sample_pool(session)
            except (
                DBAPIError,
                PoolTimeoutError,
                OSError,
                TimeoutError,
                StorageUnavailableError,
                asyncio.CancelledError,
            ):
                observation.caught(session)
                raise
    except (StorageUnavailableError, TimeoutError) as error:
        report(observation, error, deadline_expired=deadline.expired())
        if isinstance(error, TimeoutError):
            raise StorageUnavailableError from None
        raise
    finally:
        if tracked is not None:
            event.remove(tracked.sync_session, "after_begin", observation.began)


async def clock(session: AsyncSession) -> datetime:
    return (
        await session.scalars(select(cast(func.clock_timestamp(), DateTime(timezone=True))))
    ).one()


def delivery(row: DeliveryRecord) -> Delivery:
    return Delivery(row.id, row.recipient_id, Kind(row.kind), row.expires_at)


def retire(row: DeliveryRecord, state: State) -> None:
    row.state = state.value
    row.lease_token = None
    row.lease_until = None


@dataclass(frozen=True, slots=True)
class SqlStudentNotifications:
    sessions: async_sessionmaker[AsyncSession]

    async def activate(self) -> None:
        """Explicit installation boundary. Never deliver historical events before activation."""
        progress = Progress(Operation.ACTIVATE)
        async with transaction(self.sessions, progress=progress) as session:
            await session.execute(
                insert(ConsumerRecord)
                .values(
                    name="student_push_v1",
                    activated_at=await clock(session),
                )
                .on_conflict_do_nothing(index_elements=[ConsumerRecord.name])
            )

    async def materialize(self, limit: int = SOURCE_BATCH) -> int:
        if not 1 <= limit <= SOURCE_BATCH:
            raise ValueError("Bounded source batch required")
        progress = Progress(Operation.MATERIALIZE)
        async with transaction(self.sessions, progress=progress) as session:
            progress.stage = Stage.CONSUMER_LOCK
            consumer = await session.scalar(
                select(ConsumerRecord)
                .where(ConsumerRecord.name == "student_push_v1")
                .with_for_update()
            )
            if consumer is None:
                raise RuntimeError(
                    "Student notification consumer has not been explicitly activated"
                )
            progress.stage = Stage.GLOBAL_PENDING
            outstanding = (
                await session.scalars(
                    select(func.count())
                    .select_from(DeliveryRecord)
                    .where(DeliveryRecord.state.in_(ACTIVE))
                )
            ).one()
            room = min(limit, GLOBAL_PENDING - outstanding)
            if room <= 0:
                return 0
            supported = or_(
                ProductEventRecord.kind == "message.confirmed",
                and_(
                    ProductEventRecord.kind == "request.changed",
                    or_(
                        ProductEventRecord.connection_request_state == "accepted",
                        and_(
                            ProductEventRecord.connection_request_state == "pending",
                            ProductEventRecord.connection_request_version == 1,
                        ),
                    ),
                ),
            )
            progress.stage = Stage.SOURCE_EVENTS
            events = (
                await session.scalars(
                    select(ProductEventRecord)
                    .where(
                        supported,
                        ProductEventRecord.occurred_at >= consumer.activated_at,
                        ~select(DeliveryRecord.id)
                        .where(DeliveryRecord.event_id == ProductEventRecord.id)
                        .exists(),
                    )
                    .order_by(ProductEventRecord.occurred_at, ProductEventRecord.id)
                    .limit(room)
                )
            ).all()
            progress.stage = Stage.CLOCK
            now = await clock(session)
            count = 0
            for event in events:
                progress.stage = Stage.SOURCE
                source = await target(session, event, now, progress=progress)
                progress.stage = Stage.RECIPIENT_PENDING
                pending = (
                    await session.scalars(
                        select(func.count())
                        .select_from(DeliveryRecord)
                        .where(
                            DeliveryRecord.recipient_id == source.recipient,
                            DeliveryRecord.state.in_(ACTIVE),
                        )
                    )
                ).one()
                # Backpressure leaves source unconsumed. No cursor can skip late commits.
                if pending >= RECIPIENT_PENDING:
                    continue
                session.add(
                    DeliveryRecord(
                        id=uuid4(),
                        event_id=event.id,
                        recipient_id=source.recipient,
                        actor_id=source.actor,
                        relationship_id=source.relationship,
                        kind=source.kind.value,
                        state=State.PENDING.value,
                        created_at=event.occurred_at,
                        due_at=now,
                        expires_at=event.occurred_at + TTL,
                        attempts=0,
                        lease_token=None,
                        lease_until=None,
                    )
                )
                progress.stage = Stage.DELIVERY_FLUSH
                await session.flush()
                count += 1
            return count

    async def claim(self) -> Claim | None:
        progress = Progress(Operation.CLAIM)
        async with transaction(self.sessions, progress=progress) as session:
            now = await clock(session)
            row = await session.scalar(
                select(DeliveryRecord)
                .where(
                    or_(
                        and_(
                            DeliveryRecord.state == State.PENDING.value,
                            DeliveryRecord.due_at <= now,
                        ),
                        and_(
                            DeliveryRecord.state.in_((State.CLAIMED.value, State.SENDING.value)),
                            DeliveryRecord.lease_until <= now,
                        ),
                    )
                )
                .order_by(DeliveryRecord.due_at, DeliveryRecord.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if row is None:
                return None
            if row.state == State.SENDING.value:
                # Crash after durable dispatch boundary: outcome cannot be known/replayed.
                retire(row, State.UNKNOWN)
                return None
            if row.expires_at <= now:
                retire(row, State.CANCELLED)
                return None
            row.state = State.CLAIMED.value
            row.lease_token = uuid4()
            row.lease_until = now + LEASE
            return Claim(delivery(row), row.lease_token, row.lease_until)

    async def authorize(self, claim: Claim) -> Delivery | None:
        progress = Progress(Operation.AUTHORIZE)
        async with transaction(self.sessions, progress=progress) as session:
            progress.stage = Stage.HINT
            hint = await session.get(DeliveryRecord, claim.delivery.id)
            if hint is None:
                return None
            participants = sorted((hint.actor_id, hint.recipient_id))
            # Canonical core order: accounts by UUID, then relationship, then local lease.
            progress.stage = Stage.ACCOUNTS_LOCK
            accounts = (
                await session.scalars(
                    select(AccountRecord)
                    .where(AccountRecord.id.in_(participants))
                    .order_by(AccountRecord.id)
                    .with_for_update(key_share=True)
                )
            ).all()
            progress.stage = Stage.RELATIONSHIP_LOCK
            await session.execute(
                select(RelationshipRecord.id)
                .where(RelationshipRecord.id == hint.relationship_id)
                .with_for_update()
            )
            progress.stage = Stage.DELIVERY_LOCK
            row = await session.scalar(
                select(DeliveryRecord)
                .where(DeliveryRecord.id == hint.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            progress.stage = Stage.CLOCK
            now = await clock(session)
            if (
                row is None
                or row.state != State.CLAIMED.value
                or row.lease_token != claim.token
                or row.lease_until is None
                or row.lease_until <= now
            ):
                return None
            allowed = row.expires_at > now and len(accounts) == PARTICIPANTS
            for account in accounts:
                progress.stage = Stage.BINDING
                binding = await session.get(InstitutionalBindingRecord, account.id)
                if (
                    account.deleted_at is not None
                    or account.banned_at is not None
                    or binding is None
                    or binding.revoked_at is not None
                    or binding.retired_at is not None
                    or await lineage_banned(session, account.id, progress)
                ):
                    allowed = False
            progress.stage = Stage.BLOCK
            blocked = await session.scalar(
                select(BlockRevisionRecord.blocked)
                .join(
                    BlockRecord,
                    and_(
                        BlockRecord.relationship_id == BlockRevisionRecord.relationship_id,
                        BlockRecord.blocker_id == BlockRevisionRecord.blocker_id,
                        BlockRecord.current_version == BlockRevisionRecord.version,
                    ),
                )
                .where(
                    BlockRecord.relationship_id == row.relationship_id,
                    BlockRevisionRecord.blocked.is_(True),
                )
                .limit(1)
            )
            if blocked is True:
                allowed = False
            # Fresh real preference, not a cached job snapshot. Both modes permit core kinds.
            progress.stage = Stage.PREFERENCE
            mode = await session.scalar(
                select(PreferenceRevisionRecord.mode)
                .where(PreferenceRevisionRecord.account_id == row.recipient_id)
                .order_by(PreferenceRevisionRecord.version.desc())
                .limit(1)
            )
            NotificationMode(mode) if mode is not None else NotificationMode.MESSAGES_AND_REQUESTS
            progress.stage = Stage.EVENT
            event = await session.get(ProductEventRecord, row.event_id)
            if event is None:
                raise RuntimeError("Delivery lost its immutable event")
            progress.stage = Stage.SOURCE
            source = await target(session, event, now)
            allowed = (
                allowed
                and source.source_current
                and (source.recipient, source.actor, source.relationship, source.kind.value)
                == (row.recipient_id, row.actor_id, row.relationship_id, row.kind)
            )
            if not allowed:
                retire(row, State.CANCELLED)
                return None
            row.state = State.SENDING.value
            row.attempts += 1
            origin = (
                ExecutionOrigin(event.request_id, event.action_id, event.trace_id, event.span_id)
                if event.request_id is not None
                else None
            )
            # Event account is the stable request sender, not necessarily its initiator.
            actor = (
                event.request_initiator_id if event.kind == "request.changed" else event.account_id
            )
            record_authorized(delivery(row), event.id, actor, row.attempts, origin)
            return delivery(row)

    async def finish(self, claim: Claim, outcome: Outcome) -> bool:
        progress = Progress(Operation.FINISH)
        async with transaction(self.sessions, progress=progress) as session:
            row = await session.scalar(
                select(DeliveryRecord)
                .where(DeliveryRecord.id == claim.delivery.id)
                .with_for_update()
            )
            now = await clock(session)
            if (
                row is None
                or row.state != State.SENDING.value
                or row.lease_token != claim.token
                or row.lease_until is None
                or row.lease_until <= now
            ):
                return False
            state = completion(State(row.state), outcome, row.attempts, row.expires_at <= now)
            retire(row, state)
            if state == State.PENDING:
                row.due_at = now + timedelta(seconds=10 * 2 ** (row.attempts - 1))
            record_completed(outcome)
            return True


async def lineage_banned(session: AsyncSession, account_id: UUID, progress: Progress) -> bool:
    progress.stage = Stage.LINEAGE
    return await identity_lineage_banned(session, account_id)
