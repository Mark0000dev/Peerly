"""Finite synthetic support source history; never calls providers or sends mail."""

from collections.abc import Mapping
from datetime import timedelta
from hashlib import sha256
from uuid import UUID

from operator_retained_fixture import SOURCE_TIME, retained_id
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from studymate.infrastructure.support.models import (
    SupportCaseRecord,
    SupportProofRecord,
    SupportRevisionRecord,
)


async def seed_support_records(
    engine: AsyncEngine, namespace: str, targets: Mapping[str, str], viewer: UUID
) -> dict[str, str]:
    # Operator access is intentionally global. Distinct immutable source-date
    # buckets let browser scenarios isolate their real rows through public filters.
    scenario, project = namespace.split("/")[1:]
    cases = (
        "support",
        "support-references",
        "support-empty",
        "support-status",
        "support-unknown",
        "support-revocation",
        "support-replacement",
        "support-conflict",
    )
    projects = ("chromium-mobile", "webkit-mobile", "chromium-desktop")
    source_time = SOURCE_TIME + timedelta(
        days=cases.index(scenario) * 3 + projects.index(project)
    )
    ids = {
        "support_received_from": source_time.isoformat(),
        "support_received_before": (source_time + timedelta(days=1)).isoformat(),
        "support_case_id": str(retained_id(namespace, "support-0")),
        "support_anonymous_id": str(retained_id(namespace, "support-1")),
        "support_retained_id": str(retained_id(namespace, "support-2")),
        "support_missing_id": str(retained_id(namespace, "support-missing")),
    }
    if namespace.split("/")[1] == "support-empty":
        return ids
    topics = (
        "cannot_sign_in",
        "email_not_accepted",
        "code_not_arriving",
        "email_already_in_use",
        "deleted_account",
        "other",
    )
    async with async_sessionmaker(engine).begin() as session:
        for index in range(53):
            digest = sha256(f"{namespace}/support-proof-{index}".encode()).digest()
            session.add(
                SupportProofRecord(
                    digest=digest,
                    source_digest=digest,
                    created_at=source_time,
                    expires_at=source_time + timedelta(days=7),
                )
            )
        await session.flush()
        for index in range(53):
            session.add(
                SupportCaseRecord(
                    id=retained_id(namespace, f"support-{index}"),
                    proof_digest=sha256(
                        f"{namespace}/support-proof-{index}".encode()
                    ).digest(),
                    actor_id=None
                    if index % 2
                    else UUID(targets["deleted_id" if index == 2 else "active_id"]),
                    topic=topics[index % len(topics)],
                    reply_address=f"synthetic-support-{index}@example.test",
                    message=f"Literal <b>support {index}</b>\nOriginal second line",
                    details=None if index % 2 else "Synthetic retained details",
                    received_at=source_time + timedelta(minutes=100 - index),
                )
            )
        await session.flush()
        for index in range(53):
            versions = 53 if index == 0 else index % 3 + 1
            for version in range(1, versions + 1):
                session.add(
                    SupportRevisionRecord(
                        case_id=retained_id(namespace, f"support-{index}"),
                        version=version,
                        status="received"
                        if version == 1
                        else "in_review"
                        if version % 2 == 0
                        else "resolved",
                        changed_at=source_time
                        + timedelta(minutes=100 - index, seconds=version),
                        changed_by_id=None if version == 1 else viewer,
                        operator_access_version=None if version == 1 else 1,
                    )
                )
    return ids
