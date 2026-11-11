"""Isolated operator read cohorts; real Google-linked grants and retained source data."""

from datetime import datetime, timedelta
from uuid import UUID, uuid4

from operator_academic_fixture import seed_academic_records
from operator_conversation_fixture import seed_conversation_records
from operator_profile_history_fixture import seed_profile_history_records
from operator_reports_fixture import seed_report_records
from operator_retained_fixture import SOURCE_TIME, retained_id, seed_retained_targets
from operator_support_fixture import seed_support_records
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from studymate.application.identity.sessions import SessionCredential
from studymate.domain.membership import GOOGLE_ISSUER
from studymate.infrastructure.operator.models import (
    OperatorAccessRecord,
    OperatorAccessRevisionRecord,
    OperatorAuditRecord,
)
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    ExternalIdentityRecord,
    SessionRecord,
)
from studymate.infrastructure.persistence.message_read_models import (
    ConversationReadPositionRecord,
    ConversationReadRevisionRecord,
)
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.security.session_digest import Sha256SessionHasher

OPERATOR_NAMESPACES = frozenset(
    f"operator/{case}/{project}"
    for case in (
        "authorized",
        "denied",
        "revocation",
        "replacement",
        "support",
        "support-references",
        "support-status",
        "support-unknown",
        "support-conflict",
        "support-empty",
        "support-revocation",
        "support-replacement",
        "history",
        "history-empty",
        "history-revocation",
        "history-replacement",
        "academic",
        "academic-empty",
        "academic-revocation",
        "academic-replacement",
        "reports",
        "reports-empty",
        "reports-revocation",
        "reports-replacement",
        "reports-events",
        "reports-reflow",
        "conversations",
        "conversations-empty",
        "conversations-revocation",
        "conversations-replacement",
    )
    for project in ("chromium-mobile", "webkit-mobile", "chromium-desktop")
)


async def _viewer(
    engine: AsyncEngine, namespace: str, *, granted: bool
) -> tuple[UUID, SessionCredential]:
    owner = retained_id(namespace, "account")
    credential = SessionCredential(uuid4().hex + uuid4().hex[:11])
    async with async_sessionmaker(engine).begin() as session:
        now = await session.scalar(select(func.clock_timestamp()))
        if not isinstance(now, datetime):
            raise TypeError("Operator fixture requires database time")
        session.add(AccountRecord(id=owner, created_at=SOURCE_TIME))
        await session.flush()
        session.add(
            ExternalIdentityRecord(
                id=retained_id(namespace, "google"),
                account_id=owner,
                issuer=GOOGLE_ISSUER,
                subject=f"synthetic-operator-{owner}",
                created_at=SOURCE_TIME,
            )
        )
        session.add(
            SessionRecord(
                id=uuid4(),
                account_id=owner,
                secret_digest=await Sha256SessionHasher().digest(credential),
                issued_at=now - timedelta(minutes=1),
                expires_at=now + timedelta(hours=1),
            )
        )
        await session.flush()
        if granted:
            session.add(OperatorAccessRecord(account_id=owner, current_version=1))
            await session.flush()
            session.add(
                OperatorAccessRevisionRecord(
                    account_id=owner,
                    version=1,
                    active=True,
                    changed_at=SOURCE_TIME
                    if namespace.split("/")[1].startswith("support")
                    else now,
                )
            )
    return owner, credential


async def seed_operator(engine: AsyncEngine, namespace: str) -> dict[str, str]:
    if namespace not in OPERATOR_NAMESPACES:
        raise ValueError("Unsupported controlled operator namespace")
    viewer, credential = await _viewer(
        engine, namespace + "/viewer", granted="/denied/" not in namespace
    )
    replacement, replacement_credential = await _viewer(
        engine, namespace + "/replacement", granted=True
    )
    targets = await seed_retained_targets(engine, namespace)
    if namespace.split("/")[1].startswith("history"):
        await seed_profile_history_records(engine, namespace, targets)
    if namespace.split("/")[1].startswith("academic"):
        await seed_academic_records(engine, namespace, targets)
    reports = (
        await seed_report_records(engine, namespace, targets)
        if namespace.split("/")[1].startswith("reports")
        else {}
    )
    conversations = (
        await seed_conversation_records(engine, namespace, targets)
        if namespace.split("/")[1].startswith("conversations")
        else {}
    )
    support = (
        await seed_support_records(engine, namespace, targets, viewer)
        if namespace.split("/")[1].startswith("support")
        else {}
    )
    return {
        **support,
        **conversations,
        **reports,
        "viewer_id": str(viewer),
        "viewer_session": credential.value,
        "replacement_id": str(replacement),
        "replacement_session": replacement_credential.value,
        **targets,
        "nullable_id": str(viewer),
    }


async def set_operator_grant(engine: AsyncEngine, owner: UUID, *, active: bool) -> None:
    async with async_sessionmaker(engine).begin() as session:
        record = await session.get(OperatorAccessRecord, owner, with_for_update=True)
        if record is None:
            raise ValueError("Controlled operator grant is absent")
        now = await session.scalar(select(func.clock_timestamp()))
        if not isinstance(now, datetime):
            raise TypeError("Operator fixture requires database time")
        version = record.current_version + 1
        session.add(
            OperatorAccessRevisionRecord(
                account_id=owner, version=version, active=active, changed_at=now
            )
        )
        await session.flush()
        record.current_version = version


async def operator_audit_summary(engine: AsyncEngine, owner: UUID) -> dict[str, int]:
    async with async_sessionmaker(engine)() as session:
        owned = select(OperatorAuditRecord.id).where(
            OperatorAuditRecord.operator_id == owner
        )
        audits = await session.scalar(
            select(func.count())
            .select_from(OperatorAuditRecord)
            .where(OperatorAuditRecord.operator_id == owner)
        )
        events = await session.scalar(
            select(func.count())
            .select_from(ProductEventRecord)
            .where(ProductEventRecord.operator_audit_id.in_(owned))
        )
        reads = await session.scalar(
            select(func.count()).select_from(ConversationReadRevisionRecord)
        )
        positions = await session.scalar(
            select(func.count()).select_from(ConversationReadPositionRecord)
        )
    if (
        not isinstance(audits, int)
        or not isinstance(events, int)
        or not isinstance(reads, int)
        or not isinstance(positions, int)
    ):
        raise TypeError("Controlled counters unavailable")
    return {
        "audits": audits,
        "linked_events": events,
        "student_reads": reads,
        "student_read_positions": positions,
    }
