"""Relational lifecycle writes; callers must hold actual account/session authority locks."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from studymate.application.idempotency import IntentKey
from studymate.application.lifecycle.intents import LifecycleIntent, LifecycleResult
from studymate.domain.lifecycle.states import AccountLifecycle, BanRevision, LifecycleOperation
from studymate.domain.operator.access import OperatorAccess
from studymate.infrastructure.lifecycle.callbacks import LifecycleEffects
from studymate.infrastructure.lifecycle.models import LifecycleIntentRecord, LifecycleRevisionRecord
from studymate.infrastructure.lifecycle.values import intent_value, revision_value
from studymate.infrastructure.observability.tracing import current_origin
from studymate.infrastructure.operator.models import OperatorAccessRevisionRecord
from studymate.infrastructure.persistence.identity_models import AccountRecord


async def read_state(session: AsyncSession, account_id: UUID) -> AccountLifecycle | None:
    row = (
        await session.execute(
            select(
                AccountRecord.id,
                AccountRecord.banned_at,
                AccountRecord.deleted_at,
                AccountRecord.lifecycle_version,
            ).where(AccountRecord.id == account_id)
        )
    ).one_or_none()
    if row is None:
        return None
    return AccountLifecycle(row.id, row.banned_at, row.deleted_at, row.lifecycle_version or 0)


async def read_intent(
    session: AsyncSession,
    actor_id: UUID,
    operation: LifecycleOperation,
    key: IntentKey,
) -> LifecycleIntent | None:
    row = await session.get(LifecycleIntentRecord, (actor_id, operation.value, key.value))
    if row is None:
        return None
    source: LifecycleResult | None = None
    if row.result_source_id is not None:
        stored = await session.get(LifecycleRevisionRecord, row.result_source_id)
        if stored is None:
            raise RuntimeError("Lifecycle intent lost its retained source")
        grant = None
        if stored.operator_access_version is not None:
            recorded = await session.get(
                OperatorAccessRevisionRecord, (stored.actor_id, stored.operator_access_version)
            )
            if recorded is None:
                raise RuntimeError("Lifecycle source lost its historical operator grant")
            grant = OperatorAccess(
                recorded.account_id, recorded.version, recorded.active, recorded.changed_at
            )
        source = revision_value(stored, grant)
    return intent_value(row, source)


async def apply_transition(
    session: AsyncSession,
    transition: LifecycleResult,
    effects: LifecycleEffects,
) -> None:
    source = transition.revision
    if source is None:
        raise RuntimeError("No-op cannot append a lifecycle source or invoke effects")
    before, after = transition.before, transition.after
    updated = await session.scalar(
        update(AccountRecord)
        .where(
            AccountRecord.id == before.account_id,
            AccountRecord.lifecycle_version.is_not_distinct_from(before.source_version or None),
            AccountRecord.banned_at.is_not_distinct_from(before.banned_at),
            AccountRecord.deleted_at.is_not_distinct_from(before.deleted_at),
        )
        .values(
            lifecycle_version=after.source_version,
            banned_at=after.banned_at,
            deleted_at=after.deleted_at,
        )
        .returning(AccountRecord.id)
    )
    if updated is None:
        raise RuntimeError("Lifecycle state changed outside the held account authority")
    origin = current_origin()
    ban = source if isinstance(source, BanRevision) else None
    session.add(
        LifecycleRevisionRecord(
            id=source.id,
            account_id=source.account_id,
            version=source.version,
            previous_version=before.source_version or None,
            operation=source.operation.value,
            before_banned_at=before.banned_at,
            before_deleted_at=before.deleted_at,
            after_banned_at=after.banned_at,
            after_deleted_at=after.deleted_at,
            changed_at=source.changed_at if isinstance(source, BanRevision) else source.deleted_at,
            actor_id=ban.operator_access.account_id if ban is not None else source.account_id,
            actor_session_id=source.actor_session_id,
            operator_access_version=ban.operator_access.version if ban is not None else None,
            operator_access_active=ban.operator_access.active if ban is not None else None,
            reason=ban.reason.value if ban is not None else None,
            workflow_id=None if isinstance(source, BanRevision) else source.workflow_id,
            http_request_id=origin.request_id if origin is not None else None,
            action_id=origin.action_id if origin is not None else None,
            trace_id=origin.trace_id if origin is not None else None,
            span_id=origin.span_id if origin is not None else None,
        )
    )
    await session.flush()
    await effects(session, transition)


async def remember_intent(
    session: AsyncSession,
    intent: LifecycleIntent,
    session_id: UUID,
    at: datetime,
) -> None:
    result = intent.result
    source = result.revision
    origin = current_origin()
    session.add(
        LifecycleIntentRecord(
            actor_id=intent.actor_id,
            operation=intent.operation.value,
            key=intent.key.value,
            target_account_id=result.after.account_id,
            submitted_session_id=session_id,
            submitted_workflow_id=(
                source.workflow_id
                if source is not None and not isinstance(source, BanRevision)
                else None
            ),
            fingerprint=intent.fingerprint,
            result_kind="changed" if source else "noop",
            result_source_id=source.id if source else None,
            noop_source_version=(result.after.source_version or None) if source is None else None,
            noop_banned_at=result.after.banned_at if source is None else None,
            noop_deleted_at=result.after.deleted_at if source is None else None,
            created_at=at,
            http_request_id=origin.request_id if origin is not None else None,
            action_id=origin.action_id if origin is not None else None,
            trace_id=origin.trace_id if origin is not None else None,
            span_id=origin.span_id if origin is not None else None,
        )
    )
    await session.flush()
