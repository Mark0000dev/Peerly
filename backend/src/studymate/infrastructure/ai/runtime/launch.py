"""Reviewed production CLI launch policy; explicit test policies live only in tests."""

from dataclasses import dataclass
from pathlib import Path

from studymate.infrastructure.ai.runtime.policy import InspectionPolicy
from studymate.infrastructure.ai.runtime.preflight import PinnedCli


@dataclass(frozen=True, slots=True)
class PinnedProcessPolicy:
    cli: PinnedCli

    async def verify(self, executable: Path, version: str) -> None:
        if executable != self.cli.executable or version != self.cli.version:
            raise ValueError("CLI policy identity mismatch")
        await self.cli.verify()

    def overrides(self, directory: Path, auth: Path) -> tuple[str, ...]:
        return InspectionPolicy(directory, auth).overrides(self.cli)
