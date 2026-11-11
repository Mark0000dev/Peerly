"""Retained relational receipts preserve historical facts without importing ORM metadata."""

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import UUID

import pytest

from studymate.domain.lifecycle.states import BanTransition, DeletionTransition
from studymate.domain.operator.access import OperatorAccess
from studymate.infrastructure.lifecycle.values import intent_value, revision_value

AT = datetime(2026, 11, 8, tzinfo=UTC)
ACTOR = UUID(int=1)
TARGET = UUID(int=2)
SESSION = UUID(int=3)
SOURCE = UUID(int=4)
WORKFLOW = UUID(int=5)
GRANT = OperatorAccess(ACTOR, 1, True, AT)


@dataclass
class Revision:
    id: UUID = SOURCE
    account_id: UUID = TARGET
    version: int = 1
    previous_version: int | None = None
    operation: str = "ban"
    before_banned_at: datetime | None = None
    before_deleted_at: datetime | None = None
    after_banned_at: datetime | None = AT
    after_deleted_at: datetime | None = None
    changed_at: datetime = AT
    actor_id: UUID = ACTOR
    actor_session_id: UUID = SESSION
    operator_access_version: int | None = 1
    operator_access_active: bool | None = True
    reason: str | None = "  exact retained reason  "
    workflow_id: UUID | None = None


@dataclass
class Intent:
    actor_id: UUID = ACTOR
    operation: str = "ban"
    key: str = "retained-intent"
    target_account_id: UUID = TARGET
    submitted_session_id: UUID = SESSION
    submitted_workflow_id: UUID | None = None
    fingerprint: bytes = b"x" * 32
    result_kind: str = "changed"
    result_source_id: UUID | None = SOURCE
    noop_source_version: int | None = None
    noop_banned_at: datetime | None = None
    noop_deleted_at: datetime | None = None


def test_ban_receipt_preserves_exact_reason_and_historical_grant() -> None:
    source = revision_value(Revision(), GRANT)
    assert isinstance(source, BanTransition)
    assert source.revision is not None
    assert source.before.source_version == 0
    assert source.revision.reason.value == "  exact retained reason  "
    assert source.revision.operator_access == GRANT
    assert intent_value(Intent(), source).result == source


def test_deletion_receipt_retains_ban_without_operator_authority() -> None:
    row = Revision(
        operation="delete",
        actor_id=TARGET,
        operator_access_version=None,
        operator_access_active=None,
        reason=None,
        workflow_id=WORKFLOW,
        before_banned_at=AT,
        after_deleted_at=AT,
    )
    source = revision_value(row, None)
    assert isinstance(source, DeletionTransition)
    assert source.after.banned_at == AT
    assert (
        intent_value(
            Intent(actor_id=TARGET, operation="delete", submitted_workflow_id=WORKFLOW), source
        ).result
        == source
    )
    with pytest.raises(RuntimeError, match="self/workflow"):
        revision_value(row, GRANT)


def test_legacy_noop_is_original_snapshot_not_a_fabricated_source() -> None:
    row = Intent(result_kind="noop", result_source_id=None, noop_banned_at=AT, noop_deleted_at=AT)
    result = intent_value(row, None).result
    assert isinstance(result, BanTransition)
    assert result.before == result.after
    assert result.revision is None
    assert result.after.source_version == 0
    assert result.after.deleted_at == AT
    with pytest.raises(RuntimeError, match="no-op"):
        intent_value(replace(row, noop_source_version=0), None)


@pytest.mark.parametrize(
    "row",
    [
        Revision(previous_version=0),
        Revision(operator_access_version=2),
        Revision(reason=None),
        Revision(workflow_id=WORKFLOW),
    ],
)
def test_corrupt_source_never_becomes_a_receipt(row: Revision) -> None:
    with pytest.raises(RuntimeError):
        revision_value(row, GRANT)


@pytest.mark.parametrize(
    "row",
    [
        Intent(submitted_session_id=UUID(int=99)),
        Intent(submitted_workflow_id=WORKFLOW),
        Intent(noop_banned_at=AT),
        Intent(result_kind="unknown"),
    ],
)
def test_corrupt_intent_never_becomes_a_receipt(row: Intent) -> None:
    with pytest.raises(RuntimeError):
        intent_value(row, revision_value(Revision(), GRANT))
