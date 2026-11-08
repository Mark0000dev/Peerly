from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.domain.registration import PolicyKind
from studymate.infrastructure.persistence.registration_models import PolicyDocumentRecord


async def documents(engine: AsyncEngine, version: str = "synthetic-test-v1") -> None:
    async with async_sessionmaker(engine).begin() as session:
        for kind in PolicyKind:
            session.add(
                PolicyDocumentRecord(
                    id=uuid4(),
                    kind=kind.value,
                    version=version,
                    title=f"Synthetic test {kind.value}",
                    content="Synthetic test document, not production legal text.",
                    published_at=datetime.now(UTC) - timedelta(days=1),
                )
            )
