from dataclasses import dataclass

import pytest

from studymate.application.check_readiness import CheckReadiness


@dataclass(frozen=True, slots=True)
class Probe:
    available: bool

    async def is_available(self) -> bool:
        return self.available


@pytest.mark.parametrize("available", [True, False])
async def test_readiness_returns_the_port_result(available: bool) -> None:
    assert await CheckReadiness(Probe(available))() is available
