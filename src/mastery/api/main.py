"""FastAPI application entrypoint."""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from mastery.api.routers import auth, health, instructor, learning
from mastery.common.config import get_settings
from mastery.common.logging import configure_logging, get_logger, request_id_var
from mastery.db.cache import cache
from mastery.db.session import init_db
from mastery.models.registry import registry

settings = get_settings()
configure_logging(settings.log_level, json_output=settings.is_production)
log = get_logger(__name__)

REQUESTS = Counter("mastery_requests_total", "HTTP requests", ["method", "path", "status"])
LATENCY = Histogram(
    "mastery_request_duration_seconds",
    "Request duration",
    ["method", "path"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.2, 0.5, 1.0, 2.5, 5.0),
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup work happens exactly once.

    Loading models here rather than per request is the difference between a 50ms endpoint
    and a 3s one.
    """
    log.info("app.starting", env=settings.app_env)
    if settings.auto_create_schema:
        await init_db()
    else:
        log.info("app.schema.managed_by_migrations")
    await cache.connect()
    registry.load()
    log.info("app.ready", model_version=registry.version, cache=cache.kind)
    yield
    log.info("app.stopping")


app = FastAPI(
    title="Mastery - Adaptive Learning Engine",
    description=(
        "Infers a per-concept mastery probability for each learner and selects the next "
        "question to maximise long-term learning gain."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=settings.cors_origin_regex or None,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def observability(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Tag every request with an id, time it, and record the metrics."""
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    token = request_id_var.set(request_id)
    route = request.scope.get("route")
    path = getattr(route, "path", request.url.path)
    started = time.perf_counter()

    try:
        response = await call_next(request)
        status_code = response.status_code
    except Exception:
        log.exception("request.unhandled_error", path=path, method=request.method)
        response = JSONResponse(
            status_code=500, content={"detail": "Internal server error", "request_id": request_id}
        )
        status_code = 500
    finally:
        elapsed = time.perf_counter() - started
        request_id_var.reset(token)

    LATENCY.labels(request.method, path).observe(elapsed)
    REQUESTS.labels(request.method, path, str(status_code)).inc()
    response.headers["x-request-id"] = request_id
    log.info(
        "request.completed",
        method=request.method,
        path=path,
        status=status_code,
        duration_ms=round(elapsed * 1000, 2),
    )
    return response


@app.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    payload: bytes = generate_latest()
    return Response(payload, media_type=CONTENT_TYPE_LATEST)


app.include_router(health.router)
app.include_router(auth.router)
app.include_router(learning.router)
app.include_router(instructor.router)


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {
        "name": "Mastery",
        "docs": "/docs",
        "health": "/health",
        "model_version": registry.version,
    }
