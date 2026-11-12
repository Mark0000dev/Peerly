from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.policy_history.read import ReadPolicyHistory
from studymate.domain.registration import PolicyKind
from studymate.infrastructure.persistence.registration_models import PolicyDocumentRecord
from studymate.infrastructure.policy_history.read import SqlPolicyHistoryUnitOfWork

pytestmark = pytest.mark.integration


async def test_public_history_pages_actual_metadata_and_excludes_future_and_other_kind(
    identity_engine: AsyncEngine,
) -> None:
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    now = datetime.now(UTC)
    async with sessions.begin() as session:
        for number, kind, at in (
            (1, "terms", now - timedelta(days=1)),
            (2, "terms", now - timedelta(days=1)),
            (3, "privacy", now - timedelta(days=1)),
            (4, "terms", now + timedelta(days=1)),
        ):
            session.add(
                PolicyDocumentRecord(
                    id=UUID(int=number),
                    kind=kind,
                    version=f"history-{number}",
                    title=f"Published title {number}",
                    content="Actual legal document text",
                    published_at=at,
                )
            )
    read = ReadPolicyHistory(SqlPolicyHistoryUnitOfWork(sessions))
    first = await read(PolicyKind.TERMS, limit=1)
    assert [item.reference.id for item in first.items] == [UUID(int=2)]
    assert first.next_position is not None
    second = await read(PolicyKind.TERMS, first.next_position, limit=1)
    assert [item.reference.id for item in second.items] == [UUID(int=1)]
    assert second.next_position is None
    assert second.items[0].title == "Published title 1"
    assert (await read(PolicyKind.PRIVACY)).items[0].reference.id == UUID(int=3)
