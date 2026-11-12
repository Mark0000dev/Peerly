"""Read-only released-model projections and native catalogue domain mapping."""

import asyncio

from deployment.restore.accept_restore import MAX_TABLES, RejectedError
from deployment.restore.recovery_checks import target_guard
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from studymate.infrastructure.persistence.catalogue import SqlSubjectReader
from studymate.infrastructure.persistence.catalogue_models import SubjectRecord
from studymate.infrastructure.persistence.schema import metadata


async def probe(engine: AsyncEngine, *, source: str, target: str) -> dict[str, object]:
    """Caller supplies an isolated engine, not ambient app/provider configuration.

    No authentication bypass is exposed: this is an offline repository/domain
    compatibility check, not an authenticated user journey or a successful restore.
    """
    target_guard(source, target)
    if (
        engine.url.database != target
        or engine.url.drivername != "postgresql+asyncpg"
        or engine.url.host not in {"127.0.0.1", "::1"}
        or engine.url.query
    ):
        raise RejectedError("recovery_engine_identity")
    tables = tuple(metadata.sorted_tables)
    if not 0 < len(tables) <= MAX_TABLES:
        raise RejectedError("application_table_bound")
    async with asyncio.timeout(90), engine.connect() as connection, connection.begin():
        await connection.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        await connection.execute(text("SET LOCAL statement_timeout='2s'"))
        await connection.execute(text("SET LOCAL lock_timeout='1s'"))
        await connection.execute(text("SET LOCAL search_path=public,pg_catalog"))
        actual = await connection.scalar(text("SELECT current_database()"))
        if actual != target:
            raise RejectedError("recovery_connected_identity")
        for table in tables:
            # Resolve every actual released model column/type through PostgreSQL.
            await connection.execute(select(table).limit(0))
        async with AsyncSession(bind=connection, expire_on_commit=False) as session:
            ids = tuple(
                await session.scalars(select(SubjectRecord.id).order_by(SubjectRecord.id).limit(50))
            )
            if not ids:
                raise RejectedError("application_catalogue_empty")
            subjects = await SqlSubjectReader(session).get_many(ids)
            if {subject.id for subject in subjects} != set(ids):
                raise RejectedError("application_catalogue_mapping")
        return {
            "status": "released_model_projection_catalogue_mapping",
            "tables_projected": len(tables),
            "subjects_mapped": len(subjects),
            "full_restore_proven": False,
            "authenticated_journeys_proven": False,
        }
