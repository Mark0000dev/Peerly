"""Reviewed request persistence shapes; registration/migration belong to main owner.

Do not import in shared tests before paired migration/conversation FK alignment.
"""

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from studymate.infrastructure.persistence.base import Base

STATE_CHECK = (
    "state IN ('pending','pending_decline','declined','withdrawn',"
    "'expired','unavailable','accepted')"
)


class RequestPreviewRecord(Base):
    __tablename__ = "request_previews"
    __table_args__ = (
        UniqueConstraint(
            "id", "sender_id", "recipient_id", name="uq_request_previews_participants"
        ),
        ForeignKeyConstraint(
            ["sender_id", "sender_goal_id", "sender_goal_version"],
            ["goal_revisions.account_id", "goal_revisions.goal_id", "goal_revisions.version"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["recipient_id", "recipient_goal_id", "recipient_goal_version"],
            ["goal_revisions.account_id", "goal_revisions.goal_id", "goal_revisions.version"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["sender_id", "sender_help_version"],
            ["help_revisions.account_id", "help_revisions.version"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["recipient_id", "recipient_help_version"],
            ["help_revisions.account_id", "help_revisions.version"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("sender_id <> recipient_id", name="distinct_participants"),
        CheckConstraint("mode IN ('find_help','offer_help','study_together')", name="request_mode"),
        CheckConstraint("octet_length(source_json) BETWEEN 1 AND 32768", name="bounded_source"),
        CheckConstraint("jsonb_typeof(source_json::jsonb) = 'object'", name="source_object"),
        CheckConstraint(
            "(sender_goal_id IS NULL) = (sender_goal_version IS NULL) AND "
            "(recipient_goal_id IS NULL) = (recipient_goal_version IS NULL)",
            name="complete_goal_refs",
        ),
        CheckConstraint(
            "(sender_goal_version IS NULL OR sender_goal_version > 0) AND "
            "(recipient_goal_version IS NULL OR recipient_goal_version > 0) AND "
            "(sender_help_version IS NULL OR sender_help_version > 0) AND "
            "(recipient_help_version IS NULL OR recipient_help_version > 0)",
            name="positive_source_versions",
        ),
        CheckConstraint(
            "(mode='find_help' AND sender_goal_id IS NOT NULL AND recipient_goal_id IS "
            "NULL AND sender_help_version IS NULL AND recipient_help_version IS NOT NULL) "
            "OR (mode='offer_help' AND sender_goal_id IS NULL AND recipient_goal_id IS "
            "NOT NULL AND sender_help_version IS NOT NULL AND recipient_help_version IS "
            "NULL) OR (mode='study_together' AND sender_goal_id IS NOT NULL AND "
            "recipient_goal_id IS NOT NULL AND sender_help_version IS NULL AND "
            "recipient_help_version IS NULL)",
            name="mode_sources",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    sender_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"))
    recipient_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"))
    mode: Mapped[str] = mapped_column(String(24))
    subject_id: Mapped[UUID] = mapped_column(ForeignKey("subjects.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_json: Mapped[str] = mapped_column(Text)
    sender_goal_id: Mapped[UUID | None] = mapped_column()
    sender_goal_version: Mapped[int | None] = mapped_column()
    recipient_goal_id: Mapped[UUID | None] = mapped_column()
    recipient_goal_version: Mapped[int | None] = mapped_column()
    sender_help_version: Mapped[int | None] = mapped_column()
    recipient_help_version: Mapped[int | None] = mapped_column()


class ConnectionRequestRecord(Base):
    __tablename__ = "connection_requests"
    __table_args__ = (
        UniqueConstraint("id", "relationship_id", name="uq_connection_requests_relationship"),
        UniqueConstraint(
            "id", "sender_id", "recipient_id", name="uq_connection_requests_participants"
        ),
        UniqueConstraint("sender_id", "decision_sequence", name="uq_connection_requests_decision"),
        ForeignKeyConstraint(
            ["relationship_id", "low_id", "high_id"],
            ["relationships.id", "relationships.low_id", "relationships.high_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["preview_id", "sender_id", "recipient_id"],
            ["request_previews.id", "request_previews.sender_id", "request_previews.recipient_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["id", "current_version", "state"],
            [
                "request_revisions.request_id",
                "request_revisions.version",
                "request_revisions.state",
            ],
            name="fk_connection_requests_current_revision",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
            ondelete="RESTRICT",
        ),
        CheckConstraint("low_id < high_id", name="canonical_pair"),
        CheckConstraint(
            "(sender_id=low_id AND recipient_id=high_id) OR (sender_id=high_id AND "
            "recipient_id=low_id)",
            name="directional_participants",
        ),
        CheckConstraint(STATE_CHECK, name="request_state"),
        CheckConstraint("current_version > 0 AND decision_sequence > 0", name="positive_versions"),
        CheckConstraint("expires_at > sent_at", name="valid_expiry"),
        CheckConstraint("length(request_text) BETWEEN 1 AND 240", name="request_text_length"),
        CheckConstraint("note IS NULL OR length(note) BETWEEN 1 AND 240", name="note_length"),
        Index(
            "uq_connection_requests_pending_pair",
            "relationship_id",
            unique=True,
            postgresql_where=text("state IN ('pending','pending_decline')"),
        ),
        Index("ix_connection_requests_sender_state", "sender_id", "state", "sent_at"),
        Index("ix_connection_requests_recipient_state", "recipient_id", "state", "sent_at"),
        Index(
            "ix_connection_requests_pending_expiry",
            "expires_at",
            postgresql_where=text("state IN ('pending','pending_decline')"),
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    relationship_id: Mapped[UUID] = mapped_column()
    low_id: Mapped[UUID] = mapped_column()
    high_id: Mapped[UUID] = mapped_column()
    sender_id: Mapped[UUID] = mapped_column()
    recipient_id: Mapped[UUID] = mapped_column()
    preview_id: Mapped[UUID] = mapped_column()
    request_text: Mapped[str] = mapped_column(String(240))
    note: Mapped[str | None] = mapped_column(String(240))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    current_version: Mapped[int] = mapped_column()
    state: Mapped[str] = mapped_column(String(24))
    decision_sequence: Mapped[int] = mapped_column(BigInteger)
    request_id: Mapped[UUID | None] = mapped_column()
    action_id: Mapped[UUID | None] = mapped_column()
    trace_id: Mapped[str | None] = mapped_column(String(32))
    span_id: Mapped[str | None] = mapped_column(String(16))


class RequestRevisionRecord(Base):
    __tablename__ = "request_revisions"
    __table_args__ = (
        UniqueConstraint("request_id", "version", "state", name="uq_request_revisions_state"),
        ForeignKeyConstraint(
            ["conversation_id", "request_id"],
            ["conversations.id", "conversations.request_id"],
            name="fk_request_revisions_conversation",
            deferrable=True,
            initially="DEFERRED",
            ondelete="RESTRICT",
        ),
        CheckConstraint("version > 0", name="positive_version"),
        CheckConstraint(STATE_CHECK, name="request_state"),
        CheckConstraint("version <> 1 OR state = 'pending'", name="initial_pending"),
        CheckConstraint(
            "(state = 'pending_decline') = (decline_until IS NOT NULL)",
            name="decline_deadline_state",
        ),
        CheckConstraint(
            "decline_until IS NULL OR decline_until = changed_at + interval '10 seconds'",
            name="fixed_undo_window",
        ),
        CheckConstraint(
            "(state = 'accepted') = (conversation_id IS NOT NULL)",
            name="actual_accepted_conversation",
        ),
        Index(
            "ix_request_revisions_due_decline",
            "decline_until",
            postgresql_where=text("state = 'pending_decline'"),
        ),
    )
    request_id: Mapped[UUID] = mapped_column(
        ForeignKey("connection_requests.id", ondelete="RESTRICT"), primary_key=True
    )
    version: Mapped[int] = mapped_column(primary_key=True)
    state: Mapped[str] = mapped_column(String(24))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    decline_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    conversation_id: Mapped[UUID | None] = mapped_column()


class RequestSendDayRecord(Base):
    __tablename__ = "request_send_days"
    __table_args__ = (CheckConstraint("successful_count > 0", name="positive_count"),)
    sender_id: Mapped[UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), primary_key=True
    )
    local_day: Mapped[date] = mapped_column(primary_key=True)
    successful_count: Mapped[int] = mapped_column(BigInteger)


class RequestCommandIntentRecord(Base):
    __tablename__ = "request_command_intents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["result_preview_id", "actor_id", "peer_id"],
            ["request_previews.id", "request_previews.sender_id", "request_previews.recipient_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["result_request_id", "result_request_version", "result_request_state"],
            [
                "request_revisions.request_id",
                "request_revisions.version",
                "request_revisions.state",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["result_request_id", "result_sender_id", "result_recipient_id"],
            [
                "connection_requests.id",
                "connection_requests.sender_id",
                "connection_requests.recipient_id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["result_conversation_id", "result_request_id"],
            ["conversations.id", "conversations.request_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["result_view_ack_id", "actor_id", "result_request_id", "result_request_version"],
            [
                "request_view_acknowledgements.id",
                "request_view_acknowledgements.viewer_id",
                "request_view_acknowledgements.request_id",
                "request_view_acknowledgements.stored_version",
            ],
            ondelete="RESTRICT",
            name="fk_request_command_intents_owned_view_ack",
        ),
        CheckConstraint("key ~ '^[A-Za-z0-9_-]{8,128}$'", name="intent_key_shape"),
        CheckConstraint("octet_length(fingerprint) = 32", name="fingerprint_length"),
        CheckConstraint("actor_id <> peer_id", name="distinct_participants"),
        CheckConstraint(
            "operation IN ('preview','send','decline','undo','withdraw','accept','viewed')",
            name="operation_kind",
        ),
        CheckConstraint(
            "result_kind IN "
            "('preview','sent','outgoing','incoming','connected','request','accepted','viewed')",
            name="result_kind",
        ),
        CheckConstraint(
            "(result_request_id IS NULL) = (result_request_version IS NULL) AND "
            "(result_request_id IS NULL) = (result_request_state IS NULL) AND "
            "(result_request_id IS NULL) = (result_sender_id IS NULL) AND "
            "(result_request_id IS NULL) = (result_recipient_id IS NULL)",
            name="complete_request_result",
        ),
        CheckConstraint(
            "(((operation='preview' AND result_kind='preview' AND result_preview_id IS NOT "
            "NULL AND result_request_id IS NULL AND result_conversation_id IS NULL) OR "
            "((operation='send' AND result_kind IN ('sent','outgoing','incoming') OR "
            "(operation='preview' AND result_kind IN ('outgoing','incoming'))) AND "
            "result_preview_id IS NULL AND result_request_id IS NOT NULL AND "
            "result_request_state IN ('pending','pending_decline') AND "
            "result_conversation_id IS NULL) OR (operation IN ('preview','send') AND "
            "result_kind='connected' AND result_preview_id IS NULL AND result_request_id "
            "IS NOT NULL AND result_request_state='accepted' AND result_conversation_id "
            "IS NOT NULL) OR (operation IN ('decline','undo','withdraw') AND "
            "result_kind='request' AND result_preview_id IS NULL AND result_request_id IS "
            "NOT NULL AND result_conversation_id IS NULL AND ((operation='decline' AND "
            "result_request_state='pending_decline') OR (operation='undo' AND "
            "result_request_state='pending') OR (operation='withdraw' AND "
            "result_request_state='withdrawn'))) OR (operation='accept' AND "
            "result_kind='accepted' AND result_preview_id IS NULL AND result_request_id "
            "IS NOT NULL AND result_request_state='accepted' AND result_conversation_id "
            "IS NOT NULL)) AND result_view_ack_id IS NULL) OR (operation='viewed' AND "
            "result_kind='viewed' AND result_preview_id IS NULL AND result_request_id IS NOT NULL "
            "AND result_conversation_id IS NULL AND result_view_ack_id IS NOT NULL)",
            name="typed_operation_result",
        ),
        CheckConstraint(
            "result_request_id IS NULL OR ((actor_id=result_sender_id AND "
            "peer_id=result_recipient_id) OR (actor_id=result_recipient_id AND "
            "peer_id=result_sender_id))",
            name="owned_result_pair",
        ),
        CheckConstraint(
            "result_kind NOT IN ('sent','outgoing') OR (actor_id=result_sender_id AND "
            "peer_id=result_recipient_id)",
            name="outgoing_result_direction",
        ),
        CheckConstraint(
            "result_kind <> 'incoming' OR (actor_id=result_recipient_id AND "
            "peer_id=result_sender_id)",
            name="incoming_result_direction",
        ),
        CheckConstraint(
            "operation NOT IN ('decline','undo','accept') OR "
            "(actor_id=result_recipient_id AND peer_id=result_sender_id)",
            name="recipient_operation",
        ),
        CheckConstraint(
            "operation <> 'withdraw' OR (actor_id=result_sender_id AND "
            "peer_id=result_recipient_id)",
            name="sender_withdrawal",
        ),
    )
    actor_id: Mapped[UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), primary_key=True
    )
    operation: Mapped[str] = mapped_column(String(16), primary_key=True)
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    peer_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"))
    fingerprint: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    result_kind: Mapped[str] = mapped_column(String(16))
    result_view_ack_id: Mapped[UUID | None] = mapped_column()
    result_preview_id: Mapped[UUID | None] = mapped_column()
    result_request_id: Mapped[UUID | None] = mapped_column()
    result_request_version: Mapped[int | None] = mapped_column()
    result_request_state: Mapped[str | None] = mapped_column(String(24))
    result_sender_id: Mapped[UUID | None] = mapped_column()
    result_recipient_id: Mapped[UUID | None] = mapped_column()
    result_conversation_id: Mapped[UUID | None] = mapped_column()
    request_id: Mapped[UUID | None] = mapped_column()
    action_id: Mapped[UUID | None] = mapped_column()
    trace_id: Mapped[str | None] = mapped_column(String(32))
    span_id: Mapped[str | None] = mapped_column(String(16))


REQUEST_MODELS = (
    RequestPreviewRecord,
    ConnectionRequestRecord,
    RequestRevisionRecord,
    RequestSendDayRecord,
    RequestCommandIntentRecord,
)
