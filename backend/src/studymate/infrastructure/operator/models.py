"""Retained operator grants and audits, registered by the owner with migration0034."""

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
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from studymate.infrastructure.persistence.base import Base

ORIGIN_REQUEST_CHECK = (
    "http_request_id IS NOT NULL OR (action_id IS NULL AND trace_id IS NULL AND span_id IS NULL)"
)
ORIGIN_TRACE_CHECK = (
    "(trace_id IS NULL AND span_id IS NULL) OR "
    "(trace_id IS NOT NULL AND span_id IS NOT NULL AND "
    "trace_id ~ '^[0-9a-f]{32}$' AND trace_id != repeat('0', 32) AND "
    "span_id ~ '^[0-9a-f]{16}$' AND span_id != repeat('0', 16))"
)


class OperatorAccessRecord(Base):
    __tablename__ = "operator_access"
    __table_args__ = (
        ForeignKeyConstraint(
            ["account_id"],
            ["external_identities.account_id"],
            name="fk_operator_access_google_link",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["account_id", "current_version"],
            ["operator_access_revisions.account_id", "operator_access_revisions.version"],
            name="fk_operator_access_current_revision",
            ondelete="RESTRICT",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint("current_version > 0", name="positive_revision"),
    )
    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), primary_key=True
    )
    current_version: Mapped[int] = mapped_column()


class OperatorAccessRevisionRecord(Base):
    __tablename__ = "operator_access_revisions"
    __table_args__ = (
        UniqueConstraint(
            "account_id", "version", "active", name="uq_operator_access_revisions_state"
        ),
        CheckConstraint(ORIGIN_REQUEST_CHECK, name="origin_request_context"),
        CheckConstraint(ORIGIN_TRACE_CHECK, name="origin_trace_pair"),
        CheckConstraint("version > 0", name="positive_revision"),
    )
    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("operator_access.account_id", ondelete="RESTRICT"), primary_key=True
    )
    version: Mapped[int] = mapped_column(primary_key=True)
    active: Mapped[bool] = mapped_column()
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    changed_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT")
    )
    http_request_id: Mapped[UUID | None] = mapped_column()
    action_id: Mapped[UUID | None] = mapped_column()
    trace_id: Mapped[str | None] = mapped_column(String(32))
    span_id: Mapped[str | None] = mapped_column(String(16))


OPERATOR_INSPECTION_SHAPE = (
    "(((((action='search_accounts' AND resource_kind='account' AND requested_id IS NULL AND o"
    "utcome='search' AND query_fingerprint IS NOT NULL AND octet_length(query_fingerprint)=32"
    " AND cardinality(result_ids)<=20) OR (action='read_account' AND resource_kind='account' "
    "AND requested_id IS NOT NULL AND query_fingerprint IS NULL AND ((outcome='read' AND resu"
    "lt_ids=ARRAY[requested_id]) OR (outcome='not_found' AND cardinality(result_ids)=0))) OR "
    "(action='read_conversation_messages' AND resource_kind='conversation' AND requested_id I"
    "S NOT NULL AND query_fingerprint IS NULL AND ((outcome='read' AND cardinality(result_ids"
    ")<=50) OR (outcome='not_found' AND cardinality(result_ids)=0)))) OR (action='search_even"
    "ts' AND resource_kind='event' AND requested_id IS NULL AND outcome='search' AND query_fi"
    "ngerprint IS NOT NULL AND octet_length(query_fingerprint)=32 AND cardinality(result_ids)"
    "<=50) OR (action IN ('read_event','read_audit') AND resource_kind=CASE WHEN action='read"
    "_event' THEN 'event' ELSE 'audit' END AND requested_id IS NOT NULL AND query_fingerprint"
    " IS NULL AND ((outcome='read' AND result_ids=ARRAY[requested_id]) OR (outcome='not_found"
    "' AND cardinality(result_ids)=0)))) OR (action='search_reports' AND resource_kind='repor"
    "t' AND requested_id IS NULL AND outcome='search' AND query_fingerprint IS NOT NULL AND o"
    "ctet_length(query_fingerprint)=32 AND cardinality(result_ids)<=50) OR (action='read_repo"
    "rt' AND resource_kind='report' AND requested_id IS NOT NULL AND query_fingerprint IS NUL"
    "L AND ((outcome='read' AND result_ids=ARRAY[requested_id]) OR (outcome='not_found' AND c"
    "ardinality(result_ids)=0)))) AND requested_media_owner_id IS NULL AND requested_media_at"
    "tempt_id IS NULL AND requested_media_kind IS NULL AND actual_source_upload_id IS NULL) O"
    "R (action='read_media' AND resource_kind='profile_media' AND requested_id IS NOT NULL AN"
    "D query_fingerprint IS NULL AND requested_media_owner_id IS NOT NULL AND requested_media"
    "_attempt_id IS NOT NULL AND requested_media_kind IS NOT NULL AND requested_media_kind IN"
    " ('original','display') AND ((outcome='read' AND result_ids=ARRAY[requested_id] AND actu"
    "al_source_upload_id IS NOT NULL AND actual_source_upload_id=requested_id) OR (outcome='n"
    "ot_found' AND cardinality(result_ids)=0 AND (actual_source_upload_id IS NULL OR actual_s"
    "ource_upload_id=requested_id))))"
)


_BEFORE_SUPPORT_INSPECTION_SHAPE = OPERATOR_INSPECTION_SHAPE
OPERATOR_INSPECTION_SHAPE = (
    f"({_BEFORE_SUPPORT_INSPECTION_SHAPE}) OR ("
    "action='read_support_case' AND resource_kind='support_case' AND "
    "requested_id IS NOT NULL AND query_fingerprint IS NULL AND "
    "requested_media_owner_id IS NULL AND requested_media_attempt_id IS NULL AND "
    "requested_media_kind IS NULL AND actual_source_upload_id IS NULL AND "
    "((outcome='read' AND result_ids=ARRAY[requested_id]) OR "
    "(outcome='not_found' AND cardinality(result_ids)=0)))"
)


_BEFORE_SUPPORT_SEARCH_INSPECTION_SHAPE = OPERATOR_INSPECTION_SHAPE
OPERATOR_INSPECTION_SHAPE = (
    f"({_BEFORE_SUPPORT_SEARCH_INSPECTION_SHAPE}) OR ("
    "action='search_support_cases' AND resource_kind='support_case' AND requested_id IS "
    "NULL AND outcome='search' AND query_fingerprint IS NOT NULL AND "
    "octet_length(query_fingerprint)=32 AND cardinality(result_ids)<=50 AND "
    "requested_media_owner_id IS NULL AND requested_media_attempt_id IS NULL AND "
    "requested_media_kind IS NULL AND actual_source_upload_id IS NULL"
    ")"
)


class OperatorAuditRecord(Base):
    __tablename__ = "operator_audits"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "operator_id",
            "operator_access_version",
            "action",
            name="uq_operator_audits_source",
        ),
        ForeignKeyConstraint(
            ["operator_id", "operator_access_version", "operator_access_active"],
            [
                "operator_access_revisions.account_id",
                "operator_access_revisions.version",
                "operator_access_revisions.active",
            ],
            name="fk_operator_audits_actual_active_revision",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["actual_source_upload_id", "requested_media_owner_id"],
            ["photo_uploads.id", "photo_uploads.account_id"],
            name="fk_operator_audit_media_owner_source",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["actual_source_upload_id", "requested_media_attempt_id"],
            ["photo_processing_attempts.upload_id", "photo_processing_attempts.id"],
            name="fk_operator_audit_media_attempt_source",
            ondelete="RESTRICT",
        ),
        CheckConstraint("operator_access_active IS TRUE", name="active_grant_source"),
        CheckConstraint(ORIGIN_REQUEST_CHECK, name="origin_request_context"),
        CheckConstraint(ORIGIN_TRACE_CHECK, name="origin_trace_pair"),
        CheckConstraint(
            "cardinality(result_ids)=0 OR array_ndims(result_ids)=1",
            name="one_dimensional_result_ids",
        ),
        Index("ix_operator_audits_actor_time", "operator_id", "occurred_at", "id"),
        Index(
            "ix_operator_audits_resource_time", "resource_kind", "requested_id", "occurred_at", "id"
        ),
        CheckConstraint(
            "cardinality(result_ids) BETWEEN 0 AND 50 AND array_position(result_ids, NULL) IS NULL",
            name="bounded_result_ids",
        ),
        CheckConstraint(OPERATOR_INSPECTION_SHAPE, name="fixed_inspection_shape"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    operator_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"))
    operator_access_version: Mapped[int] = mapped_column()
    operator_access_active: Mapped[bool] = mapped_column()
    action: Mapped[str] = mapped_column(String(32))
    resource_kind: Mapped[str] = mapped_column(String(16))
    requested_id: Mapped[UUID | None] = mapped_column()
    result_ids: Mapped[list[UUID]] = mapped_column(ARRAY(PG_UUID(as_uuid=True)))
    outcome: Mapped[str] = mapped_column(String(16))
    query_fingerprint: Mapped[bytes | None] = mapped_column(LargeBinary)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    http_request_id: Mapped[UUID | None] = mapped_column()
    action_id: Mapped[UUID | None] = mapped_column()
    trace_id: Mapped[str | None] = mapped_column(String(32))
    span_id: Mapped[str | None] = mapped_column(String(16))

    requested_media_owner_id: Mapped[UUID | None] = mapped_column()
    requested_media_attempt_id: Mapped[UUID | None] = mapped_column()
    requested_media_kind: Mapped[str | None] = mapped_column(String(16))
    actual_source_upload_id: Mapped[UUID | None] = mapped_column()
