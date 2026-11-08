from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from studymate.domain.catalogue import Subject
from studymate.infrastructure.persistence.catalogue_models import SubjectAliasRecord, SubjectRecord


@dataclass(frozen=True, slots=True)
class SqlSubjectReader:
    session: AsyncSession

    async def get(self, subject_id: UUID, *, lock: bool = False) -> Subject | None:
        found = await self.get_many((subject_id,), lock=lock)
        return found[0] if found else None

    async def get_many(
        self, subject_ids: tuple[UUID, ...], *, lock: bool = False
    ) -> tuple[Subject, ...]:
        if not subject_ids:
            return ()
        query = (
            select(SubjectRecord)
            .where(SubjectRecord.id.in_(subject_ids))
            .order_by(SubjectRecord.id)
        )
        if lock:
            query = query.with_for_update(read=True)
        records = tuple(await self.session.scalars(query))
        aliases: dict[UUID, list[str]] = {record.id: [] for record in records}
        if records:
            values = await self.session.scalars(
                select(SubjectAliasRecord)
                .where(SubjectAliasRecord.subject_id.in_(tuple(aliases)))
                .order_by(SubjectAliasRecord.subject_id, SubjectAliasRecord.slot)
            )
            for alias in values:
                aliases[alias.subject_id].append(alias.name)
        return tuple(
            Subject(
                record.id,
                record.name,
                tuple(aliases[record.id]),
                record.created_at,
                record.archived_at,
            )
            for record in records
        )
