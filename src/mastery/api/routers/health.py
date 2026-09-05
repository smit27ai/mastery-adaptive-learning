"""Liveness and readiness.

They are different questions and must stay separate endpoints:
  /health - is the process alive? (restart me if not)
  /ready  - can it actually serve traffic? (do not route to me if not)
"""

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from mastery.common.schemas import HealthResponse, ReadyResponse
from mastery.db.cache import cache
from mastery.db.session import engine
from mastery.models.registry import registry

router = APIRouter(tags=["ops"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", version=registry.version)


@router.get("/ready", response_model=ReadyResponse)
async def ready(response: Response) -> ReadyResponse:
    checks: dict[str, str] = {}

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc}"

    checks["cache"] = f"ok ({cache.kind})" if await cache.healthy() else "degraded"
    checks["models"] = "ok" if registry.ready else "not loaded"

    # A degraded cache is survivable; a missing database or model is not.
    ok = checks["database"] == "ok" and checks["models"] == "ok"
    if not ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadyResponse(ready=ok, checks=checks)
