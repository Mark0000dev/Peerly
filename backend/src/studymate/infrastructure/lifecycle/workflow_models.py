"""Retained deletion-workflow binding; its status digest grants no application session.

Main-owned source, awaiting paired lifecycle migration45 before registry/runtime wiring.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    LargeBinary,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from studymate.infrastructure.persistence.base import Base


class AccountDeletionWorkflowRecord(Base):
    __tablename__ = "account_deletion_workflows"
    __table_args__ = (
        ForeignKeyConstraint(
            ["session_id", "account_id"],
            ["sessions.id", "sessions.account_id"],
            name="fk_deletion_workflow_actual_session",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "id", "account_id", "session_id", name="uq_deletion_workflow_owned_session"
        ),
        UniqueConstraint(
            "session_id", "generation", name="uq_deletion_workflow_session_generation"
        ),
        UniqueConstraint("status_secret_digest", name="uq_deletion_workflow_status_digest"),
        CheckConstraint("generation>0", name="positive_generation"),
        CheckConstraint("expires_at>created_at", name="valid_lifetime"),
        CheckConstraint("octet_length(status_secret_digest)=32", name="status_digest_length"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"))
    session_id: Mapped[UUID] = mapped_column()
    generation: Mapped[int] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status_secret_digest: Mapped[bytes] = mapped_column(LargeBinary)
