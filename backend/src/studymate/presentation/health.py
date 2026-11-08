from typing import Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from studymate.application.check_readiness import CheckReadiness


def health_router(check_readiness: CheckReadiness) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["health"])

    @router.get("/health")
    async def health() -> dict[str, Literal["ok"]]:
        return {"status": "ok"}

    @router.get("/ready", response_model=None)
    async def ready() -> JSONResponse:
        available = await check_readiness()
        return JSONResponse(
            {"status": "ok" if available else "unavailable"},
            status_code=200 if available else 503,
        )

    return router
