from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from studymate.infrastructure.persistence.base import Base


class DiscoveryFreshnessPolicyRecord(Base):
    __tablename__ = "discovery_freshness_policies"
    __table_args__ = (
        CheckConstraint("version > 0 AND inactivity_seconds > 0", name="positive_policy"),
    )
    version: Mapped[int] = mapped_column(primary_key=True)
    inactivity_seconds: Mapped[int] = mapped_column()
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DiscoveryExposureRecord(Base):
    __tablename__ = "discovery_exposure"
    __table_args__ = (
        ForeignKeyConstraint(
            ["account_id", "confirmation_key", "confirmed_at"],
            [
                "visibility_write_intents.account_id",
                "visibility_write_intents.key",
                "visibility_write_intents.confirmed_exposure_at",
            ],
            name="fk_discovery_exposure_actual_confirmation",
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint("inactivity_seconds > 0", name="positive_inactivity"),
        CheckConstraint("last_activity_at >= confirmed_at", name="ordered_activity"),
        CheckConstraint("paused_at IS NULL OR paused_at >= confirmed_at", name="ordered_pause"),
        Index("ix_discovery_exposure_activity", "last_activity_at", "account_id"),
    )
    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("profile_activations.account_id", ondelete="RESTRICT"), primary_key=True
    )
    inactivity_seconds: Mapped[int] = mapped_column()
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmation_key: Mapped[str | None] = mapped_column(String(128))
