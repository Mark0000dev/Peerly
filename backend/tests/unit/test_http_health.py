from dataclasses import dataclass
from http import HTTPStatus

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from studymate.application.check_readiness import CheckReadiness
from studymate.presentation.health import health_router


@dataclass(frozen=True, slots=True)
class Probe:
    available: bool

    async def is_available(self) -> bool:
        return self.available


@pytest.mark.parametrize(("available", "status"), [(True, 200), (False, 503)])
async def test_http_maps_readiness_to_status(available: bool, status: int) -> None:
    app = FastAPI()
    app.include_router(health_router(CheckReadiness(Probe(available))))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        result = await client.get("/api/ready")
    assert result.status_code == status
    assert result.json() == {"status": "ok" if available else "unavailable"}


async def test_liveness_does_not_require_a_database() -> None:
    app = FastAPI()
    app.include_router(health_router(CheckReadiness(Probe(False))))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        result = await client.get("/api/health")
    assert result.status_code == HTTPStatus.OK
    assert result.json() == {"status": "ok"}
