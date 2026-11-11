"""Retained input provenance registered by main alongside migration50."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from studymate.infrastructure.persistence.base import Base


class BootstrapCatalogueManifestRecord(Base):
    __tablename__ = "bootstrap_catalogue_manifests"
    __table_args__ = (
        CheckConstraint("version ~ '^[A-Za-z0-9._-]{1,64}$'", name="valid_version"),
        CheckConstraint("octet_length(sha256)=32", name="source_digest_length"),
        CheckConstraint(
            "sha256(convert_to(canonical_json,'UTF8'))=sha256", name="source_digest_matches"
        ),
        CheckConstraint(
            "octet_length(canonical_json) BETWEEN 1 AND 2097152", name="bounded_source"
        ),
        CheckConstraint(
            "jsonb_typeof(canonical_json::jsonb)='object' AND canonical_json::jsonb<>'{}'::jsonb",
            name="actual_source_object",
        ),
        CheckConstraint("subject_count BETWEEN 1 AND 5000", name="bounded_subject_count"),
        CheckConstraint("alias_count BETWEEN 0 AND subject_count*20", name="bounded_alias_count"),
    )
    version: Mapped[str] = mapped_column(String(64), primary_key=True)
    sha256: Mapped[bytes] = mapped_column(LargeBinary)
    canonical_json: Mapped[str] = mapped_column(Text)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    subject_count: Mapped[int] = mapped_column()
    alias_count: Mapped[int] = mapped_column()


BOOTSTRAP_DATA_MODELS = (BootstrapCatalogueManifestRecord,)
