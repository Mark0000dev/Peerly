from dataclasses import dataclass

from studymate.application.ports.database_probe import DatabaseProbe


@dataclass(frozen=True, slots=True)
class CheckReadiness:
    database: DatabaseProbe

    async def __call__(self) -> bool:
        return await self.database.is_available()
