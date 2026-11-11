from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from studymate.infrastructure.persistence.base import Base


class SubjectRecord(Base):
    __tablename__ = "subjects"
    __table_args__ = (
        UniqueConstraint("normalized_name", name="uq_subjects_normalized_name"),
        CheckConstraint(
            "length(name) BETWEEN 1 AND 80 AND length(btrim(name)) > 0", name="name_length"
        ),
        CheckConstraint("length(normalized_name) BETWEEN 1 AND 240", name="normalized_length"),
        CheckConstraint("archived_at IS NULL OR archived_at >= created_at", name="valid_archival"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    normalized_name: Mapped[str] = mapped_column(String(240))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SubjectAliasRecord(Base):
    __tablename__ = "subject_aliases"
    __table_args__ = (
        UniqueConstraint("subject_id", "normalized_alias", name="uq_subject_aliases_normalized"),
        CheckConstraint("slot BETWEEN 0 AND 19", name="bounded_slot"),
        CheckConstraint(
            "length(name) BETWEEN 1 AND 80 AND length(btrim(name)) > 0", name="name_length"
        ),
        CheckConstraint("length(normalized_alias) BETWEEN 1 AND 240", name="normalized_length"),
        Index("ix_subject_aliases_normalized", "normalized_alias"),
    )
    subject_id: Mapped[UUID] = mapped_column(
        ForeignKey("subjects.id", ondelete="RESTRICT"), primary_key=True
    )
    slot: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    normalized_alias: Mapped[str] = mapped_column(String(240))
