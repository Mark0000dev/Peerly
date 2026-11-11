from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.domain.catalogue import Subject, subject_key
from studymate.infrastructure.persistence.catalogue_models import SubjectAliasRecord, SubjectRecord


async def subject(
    engine: AsyncEngine,
    *,
    archived: bool = False,
    name: str = "Synthetic course",
    aliases: tuple[str, ...] = ("Test alias",),
) -> Subject:
    now = datetime.now(UTC)
    value = Subject(uuid4(), name, aliases, now, now if archived else None)
    async with async_sessionmaker(engine).begin() as session:
        session.add(
            SubjectRecord(
                id=value.id,
                name=value.name,
                normalized_name=subject_key(value.name),
                created_at=value.created_at,
                archived_at=value.archived_at,
            )
        )
        await session.flush()
        for slot, alias in enumerate(value.aliases):
            session.add(
                SubjectAliasRecord(
                    subject_id=value.id, slot=slot, name=alias, normalized_alias=subject_key(alias)
                )
            )
    return value
