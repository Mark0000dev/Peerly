"""Strict relational receipt decoding; no ORM import/global metadata or JSON result bag."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from studymate.application.idempotency import IntentKey
from studymate.application.lifecycle.intents import LifecycleIntent, LifecycleResult
from studymate.domain.lifecycle.states import (
    AccountLifecycle,
    BanRevision,
    BanTransition,
    DeletionRevision,
    DeletionTransition,
    LifecycleOperation,
    LifecycleReason,
)
from studymate.domain.operator.access import OperatorAccess


class RevisionRow(Protocol):
    id: UUID
    account_id: UUID
    version: int
    previous_version: int | None
    operation: str
    before_banned_at: datetime | None
    before_deleted_at: datetime | None
    after_banned_at: datetime | None
    after_deleted_at: datetime | None
    changed_at: datetime
    actor_id: UUID
    actor_session_id: UUID
    operator_access_version: int | None
    operator_access_active: bool | None
    reason: str | None
    workflow_id: UUID | None


class IntentRow(Protocol):
    actor_id: UUID
    operation: str
    key: str
    target_account_id: UUID
    submitted_session_id: UUID
    submitted_workflow_id: UUID | None
    fingerprint: bytes
    result_kind: str
    result_source_id: UUID | None
    noop_source_version: int | None
    noop_banned_at: datetime | None
    noop_deleted_at: datetime | None


def revision_value(row: RevisionRow, grant: OperatorAccess | None) -> LifecycleResult:
    operation = LifecycleOperation(row.operation)
    if row.previous_version is not None and row.previous_version < 1:
        raise RuntimeError("Lifecycle source cannot fabricate a recorded legacy version zero")
    before = AccountLifecycle(
        row.account_id,
        row.before_banned_at,
        row.before_deleted_at,
        row.previous_version if row.previous_version is not None else 0,
    )
    after = AccountLifecycle(row.account_id, row.after_banned_at, row.after_deleted_at, row.version)
    if operation == LifecycleOperation.DELETE:
        if (
            row.actor_id != row.account_id
            or row.workflow_id is None
            or row.reason is not None
            or row.operator_access_version is not None
            or row.operator_access_active is not None
            or grant is not None
        ):
            raise RuntimeError(
                "Deletion source differs from actual self/workflow/no-operator shape"
            )
        deleted = DeletionRevision(
            row.id,
            row.account_id,
            row.version,
            row.changed_at,
            row.actor_session_id,
            row.workflow_id,
        )
        return DeletionTransition(before, after, deleted)
    if (
        grant is None
        or (row.actor_id, row.operator_access_version, row.operator_access_active)
        != (grant.account_id, grant.version, grant.active)
        or row.reason is None
        or row.workflow_id is not None
    ):
        raise RuntimeError("Ban source lost its actual historical grant/private reason shape")
    banned = BanRevision(
        row.id,
        row.account_id,
        row.version,
        operation == LifecycleOperation.BAN,
        row.changed_at,
        grant,
        row.actor_session_id,
        LifecycleReason(row.reason),
    )
    return BanTransition(before, after, banned)


def intent_value(row: IntentRow, source: LifecycleResult | None) -> LifecycleIntent:
    operation = LifecycleOperation(row.operation)
    if row.result_kind == "noop":
        if (
            source is not None
            or row.result_source_id is not None
            or operation == LifecycleOperation.DELETE
            or row.submitted_workflow_id is not None
            or (row.noop_source_version is not None and row.noop_source_version < 1)
        ):
            raise RuntimeError("Lifecycle no-op differs from its actual typed retained snapshot")
        state = AccountLifecycle(
            row.target_account_id,
            row.noop_banned_at,
            row.noop_deleted_at,
            row.noop_source_version if row.noop_source_version is not None else 0,
        )
        result: LifecycleResult = BanTransition(state, state, None)
    elif row.result_kind == "changed":
        if (
            source is None
            or row.noop_source_version is not None
            or row.noop_banned_at is not None
            or row.noop_deleted_at is not None
        ):
            raise RuntimeError(
                "Changed lifecycle receipt requires only its actual immutable source"
            )
        result = source
        revision = result.revision
        if revision is None or (
            row.result_source_id,
            row.target_account_id,
            row.submitted_session_id,
            operation,
        ) != (revision.id, revision.account_id, revision.actor_session_id, revision.operation):
            raise RuntimeError(
                "Lifecycle receipt differs from exact target/session/source/operation"
            )
        workflow_id = revision.workflow_id if isinstance(revision, DeletionRevision) else None
        if row.submitted_workflow_id != workflow_id:
            raise RuntimeError("Lifecycle receipt differs from exact original workflow source")
    else:
        raise RuntimeError("Unknown lifecycle retained result kind")
    return LifecycleIntent(row.actor_id, operation, IntentKey(row.key), row.fingerprint, result)
