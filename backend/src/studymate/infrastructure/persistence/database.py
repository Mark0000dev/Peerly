from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class SqlDatabaseProbe:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def is_available(self) -> bool:
        try:
            async with self._sessions() as session:
                await session.execute(text("SELECT 1"))
        except (SQLAlchemyError, OSError):
            return False
        return True
