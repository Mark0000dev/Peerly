"""Canonical pair identity and retained, independent directional block revisions."""

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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from studymate.infrastructure.persistence.base import Base


class RelationshipRecord(Base):
    __tablename__ = "relationships"
    __table_args__ = (
        UniqueConstraint("low_id", "high_id", name="uq_relationships_pair"),
        UniqueConstraint("id", "low_id", "high_id", name="uq_relationships_participants"),
        CheckConstraint("low_id < high_id", name="canonical_pair"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    low_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"))
    high_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"))


class BlockRevisionRecord(Base):
    __tablename__ = "block_revisions"
    __table_args__ = (
        UniqueConstraint(
            "relationship_id", "blocker_id", "version", "blocked", name="uq_block_revisions_outcome"
        ),
        ForeignKeyConstraint(
            ["relationship_id", "low_id", "high_id"],
            ["relationships.id", "relationships.low_id", "relationships.high_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "relationship_id",
            "blocker_id",
            "version",
            "target_id",
            name="uq_block_revisions_target",
        ),
        CheckConstraint("version > 0", name="positive_version"),
        CheckConstraint(
            "(blocker_id = low_id AND target_id = high_id) OR "
            "(blocker_id = high_id AND target_id = low_id)",
            name="directional_participants",
        ),
    )
    relationship_id: Mapped[UUID] = mapped_column(primary_key=True)
    blocker_id: Mapped[UUID] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(primary_key=True)
    low_id: Mapped[UUID] = mapped_column()
    high_id: Mapped[UUID] = mapped_column()
    target_id: Mapped[UUID] = mapped_column()
    blocked: Mapped[bool] = mapped_column()
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class BlockRecord(Base):
    __tablename__ = "blocks"
    __table_args__ = (
        Index("ix_blocks_owner_relationship", "blocker_id", "relationship_id"),
        ForeignKeyConstraint(
            ["relationship_id", "blocker_id", "current_version"],
            [
                "block_revisions.relationship_id",
                "block_revisions.blocker_id",
                "block_revisions.version",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint("current_version > 0", name="positive_version"),
    )
    relationship_id: Mapped[UUID] = mapped_column(primary_key=True)
    blocker_id: Mapped[UUID] = mapped_column(primary_key=True)
    current_version: Mapped[int] = mapped_column()


class BlockIntentRecord(Base):
    __tablename__ = "block_write_intents"
    __table_args__ = (
        Index(
            "ix_block_write_intents_owner_target_context",
            "actor_id",
            "target_id",
            "created_at",
            "key",
            postgresql_where=text("context_id IS NOT NULL"),
        ),
        ForeignKeyConstraint(
            ["context_id", "actor_id"],
            ["profile_access_contexts.id", "profile_access_contexts.viewer_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["relationship_id", "actor_id", "result_version", "target_id"],
            [
                "block_revisions.relationship_id",
                "block_revisions.blocker_id",
                "block_revisions.version",
                "block_revisions.target_id",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint("actor_id != target_id", name="distinct_participants"),
        CheckConstraint(
            "(result_version = 0 AND relationship_id IS NULL) OR "
            "(result_version > 0 AND relationship_id IS NOT NULL)",
            name="result_shape",
        ),
        CheckConstraint("key ~ '^[A-Za-z0-9_-]{8,128}$'", name="intent_key_shape"),
        CheckConstraint("octet_length(fingerprint) = 32", name="fingerprint_length"),
    )
    actor_id: Mapped[UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), primary_key=True
    )
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    fingerprint: Mapped[bytes] = mapped_column(LargeBinary)
    target_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"))
    relationship_id: Mapped[UUID | None] = mapped_column()
    result_version: Mapped[int] = mapped_column()
    context_id: Mapped[UUID | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
