"""Paired head45 retained lifecycle sources/intents on the actual application Base.

Main owns Account.lifecycle_version, workflow models, migration and shared registry.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from studymate.infrastructure.operator.models import ORIGIN_REQUEST_CHECK, ORIGIN_TRACE_CHECK
from studymate.infrastructure.persistence.base import Base

SOURCE_TRANSITION_SHAPE = (
    "((operation='ban' AND before_banned_at IS NULL AND after_banned_at IS NOT NULL "
    "AND after_banned_at=changed_at AND after_deleted_at IS NOT DISTINCT FROM "
    "before_deleted_at) OR (operation='unban' AND before_banned_at IS NOT NULL "
    "AND after_banned_at IS NULL AND after_deleted_at IS NOT DISTINCT FROM before_deleted_at)) "
    "AND operator_access_version IS NOT NULL AND operator_access_version>0 "
    "AND operator_access_active IS TRUE AND reason IS NOT NULL "
    "AND length(reason) BETWEEN 1 AND 1000 AND reason ~ '[^[:space:]]' AND workflow_id IS NULL "
    "OR (operation='delete' AND actor_id=account_id AND before_deleted_at IS NULL "
    "AND after_deleted_at IS NOT NULL AND after_deleted_at=changed_at "
    "AND after_banned_at IS NOT DISTINCT FROM before_banned_at "
    "AND operator_access_version IS NULL AND operator_access_active IS NULL "
    "AND reason IS NULL AND workflow_id IS NOT NULL)"
)
INTENT_RESULT_SHAPE = (
    "(result_kind='changed' AND result_source_id IS NOT NULL "
    "AND noop_source_version IS NULL AND noop_banned_at IS NULL AND noop_deleted_at IS NULL) "
    "OR (result_kind='noop' AND result_source_id IS NULL AND operation IN ('ban','unban') "
    "AND (noop_source_version IS NULL OR noop_source_version>0) "
    "AND ((operation='ban' AND noop_banned_at IS NOT NULL) "
    "OR (operation='unban' AND noop_banned_at IS NULL)))"
)
INTENT_OPERATION_SHAPE = (
    "(operation IN ('ban','unban') AND submitted_workflow_id IS NULL) OR "
    "(operation='delete' AND actor_id=target_account_id "
    "AND submitted_workflow_id IS NOT NULL AND result_kind='changed')"
)


class LifecycleRevisionRecord(Base):
    __tablename__ = "account_lifecycle_revisions"
    __table_args__ = (
        UniqueConstraint("account_id", "version", name="uq_lifecycle_source_version"),
        UniqueConstraint(
            "id", "account_id", "actor_id", "operation", name="uq_lifecycle_source_intent_scope"
        ),
        UniqueConstraint("id", "actor_session_id", name="uq_lifecycle_source_session"),
        UniqueConstraint("id", "workflow_id", name="uq_lifecycle_source_workflow"),
        UniqueConstraint(
            "id",
            "actor_id",
            "account_id",
            "version",
            "operation",
            name="uq_lifecycle_source_canonical",
        ),
        ForeignKeyConstraint(
            ["account_id", "previous_version"],
            ["account_lifecycle_revisions.account_id", "account_lifecycle_revisions.version"],
            name="fk_lifecycle_previous_source",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["actor_session_id", "actor_id"],
            ["sessions.id", "sessions.account_id"],
            name="fk_lifecycle_actual_actor_session",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["actor_id", "operator_access_version", "operator_access_active"],
            [
                "operator_access_revisions.account_id",
                "operator_access_revisions.version",
                "operator_access_revisions.active",
            ],
            name="fk_lifecycle_actual_operator_grant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workflow_id", "account_id", "actor_session_id"],
            [
                "account_deletion_workflows.id",
                "account_deletion_workflows.account_id",
                "account_deletion_workflows.session_id",
            ],
            name="fk_lifecycle_actual_deletion_workflow",
            ondelete="RESTRICT",
        ),
        CheckConstraint("version>0", name="positive_source_version"),
        CheckConstraint(
            "(previous_version IS NULL AND version=1) OR "
            "(previous_version IS NOT NULL AND previous_version>0 "
            "AND version=previous_version+1)",
            name="consecutive_source_version",
        ),
        CheckConstraint("operation IN ('ban','unban','delete')", name="finite_operation"),
        CheckConstraint(SOURCE_TRANSITION_SHAPE, name="actual_transition_shape"),
        CheckConstraint(ORIGIN_REQUEST_CHECK, name="origin_request_context"),
        CheckConstraint(ORIGIN_TRACE_CHECK, name="origin_trace_pair"),
        Index("ix_lifecycle_source_actor_time", "actor_id", "changed_at", "id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"))
    version: Mapped[int] = mapped_column()
    previous_version: Mapped[int | None] = mapped_column()
    operation: Mapped[str] = mapped_column(String(6))
    before_banned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    before_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    after_banned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    after_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"))
    actor_session_id: Mapped[UUID] = mapped_column()
    operator_access_version: Mapped[int | None] = mapped_column()
    operator_access_active: Mapped[bool | None] = mapped_column()
    reason: Mapped[str | None] = mapped_column(Text)
    workflow_id: Mapped[UUID | None] = mapped_column()
    http_request_id: Mapped[UUID | None] = mapped_column()
    action_id: Mapped[UUID | None] = mapped_column()
    trace_id: Mapped[str | None] = mapped_column(String(32))
    span_id: Mapped[str | None] = mapped_column(String(16))


class LifecycleIntentRecord(Base):
    __tablename__ = "account_lifecycle_intents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["submitted_session_id", "actor_id"],
            ["sessions.id", "sessions.account_id"],
            name="fk_lifecycle_intent_actual_session",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["result_source_id", "target_account_id", "actor_id", "operation"],
            [
                "account_lifecycle_revisions.id",
                "account_lifecycle_revisions.account_id",
                "account_lifecycle_revisions.actor_id",
                "account_lifecycle_revisions.operation",
            ],
            name="fk_lifecycle_intent_actual_result",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["result_source_id", "submitted_session_id"],
            ["account_lifecycle_revisions.id", "account_lifecycle_revisions.actor_session_id"],
            name="fk_lifecycle_intent_result_session",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["result_source_id", "submitted_workflow_id"],
            ["account_lifecycle_revisions.id", "account_lifecycle_revisions.workflow_id"],
            name="fk_lifecycle_intent_result_workflow",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["target_account_id", "noop_source_version"],
            ["account_lifecycle_revisions.account_id", "account_lifecycle_revisions.version"],
            name="fk_lifecycle_intent_noop_source",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["submitted_workflow_id", "target_account_id", "submitted_session_id"],
            [
                "account_deletion_workflows.id",
                "account_deletion_workflows.account_id",
                "account_deletion_workflows.session_id",
            ],
            name="fk_lifecycle_intent_owned_workflow",
            ondelete="RESTRICT",
        ),
        CheckConstraint("operation IN ('ban','unban','delete')", name="finite_operation"),
        CheckConstraint("key ~ '^[A-Za-z0-9_-]{8,128}$'", name="bounded_intent_key"),
        CheckConstraint("octet_length(fingerprint)=32", name="actual_payload_hmac"),
        CheckConstraint("result_kind IN ('changed','noop')", name="finite_result_kind"),
        CheckConstraint(INTENT_RESULT_SHAPE, name="typed_result_snapshot"),
        CheckConstraint(INTENT_OPERATION_SHAPE, name="owned_operation_shape"),
        CheckConstraint(ORIGIN_REQUEST_CHECK, name="origin_request_context"),
        CheckConstraint(ORIGIN_TRACE_CHECK, name="origin_trace_pair"),
        Index("ix_lifecycle_intent_actor_time", "actor_id", "created_at"),
    )
    actor_id: Mapped[UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), primary_key=True
    )
    operation: Mapped[str] = mapped_column(String(6), primary_key=True)
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    target_account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"))
    submitted_session_id: Mapped[UUID] = mapped_column()
    submitted_workflow_id: Mapped[UUID | None] = mapped_column()
    fingerprint: Mapped[bytes] = mapped_column(LargeBinary)
    result_kind: Mapped[str] = mapped_column(String(7))
    result_source_id: Mapped[UUID | None] = mapped_column()
    noop_source_version: Mapped[int | None] = mapped_column()
    noop_banned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    noop_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    http_request_id: Mapped[UUID | None] = mapped_column()
    action_id: Mapped[UUID | None] = mapped_column()
    trace_id: Mapped[str | None] = mapped_column(String(32))
    span_id: Mapped[str | None] = mapped_column(String(16))


LIFECYCLE_MODELS = (LifecycleRevisionRecord, LifecycleIntentRecord)
