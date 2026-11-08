"""One retained thread per pair, bound to an actually accepted request revision."""

from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from studymate.infrastructure.persistence.base import Base


class ConversationRecord(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conversations_low_participant", "low_id", "id"),
        Index("ix_conversations_high_participant", "high_id", "id"),
        UniqueConstraint("id", "low_id", "high_id", name="uq_conversations_participants"),
        UniqueConstraint("relationship_id", name="uq_conversations_relationship"),
        UniqueConstraint("id", "request_id", name="uq_conversations_source_request"),
        ForeignKeyConstraint(
            ["relationship_id", "low_id", "high_id"],
            ["relationships.id", "relationships.low_id", "relationships.high_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["request_id", "relationship_id"],
            ["connection_requests.id", "connection_requests.relationship_id"],
            name="fk_conversations_request_relationship",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["request_id", "accepted_request_version", "request_state"],
            [
                "request_revisions.request_id",
                "request_revisions.version",
                "request_revisions.state",
            ],
            name="fk_conversations_actual_acceptance",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
            ondelete="RESTRICT",
        ),
        CheckConstraint("low_id < high_id", name="canonical_pair"),
        CheckConstraint("accepted_request_version > 1", name="accepted_revision"),
        CheckConstraint("request_state = 'accepted'", name="accepted_state"),
        CheckConstraint("next_message_sequence > 0", name="positive_message_sequence"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    relationship_id: Mapped[UUID] = mapped_column()
    low_id: Mapped[UUID] = mapped_column()
    high_id: Mapped[UUID] = mapped_column()
    request_id: Mapped[UUID] = mapped_column()
    accepted_request_version: Mapped[int] = mapped_column()
    request_state: Mapped[str] = mapped_column(String(20))
    next_message_sequence: Mapped[int] = mapped_column(BigInteger)
