"""Reviewed production CLI launch policy; explicit test policies live only in tests."""

from dataclasses import dataclass
from pathlib import Path

from studymate.infrastructure.ai.runtime.policy import (
    DEFAULT_MAX_PROCESSES,
    InspectionPolicy,
    require_max_processes,
)
from studymate.infrastructure.ai.runtime.preflight import PinnedCli


@dataclass(frozen=True, slots=True)
class PinnedProcessPolicy:
    cli: PinnedCli
    max_processes: int = DEFAULT_MAX_PROCESSES

    def __post_init__(self) -> None:
        require_max_processes(self.max_processes)

    async def verify(self, executable: Path, version: str) -> None:
        if executable != self.cli.executable or version != self.cli.version:
            raise ValueError("CLI policy identity mismatch")
        await self.cli.verify()

    def overrides(self, directory: Path, auth: Path) -> tuple[str, ...]:
        return InspectionPolicy(directory, auth, self.max_processes).overrides(self.cli)
