from __future__ import annotations

import hmac
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api import alerts, auth, messages, rooms, votes, watches, webhooks
from app.core.config import settings, validate_runtime_settings
from app.core.database import get_db, init_db
from app.integrations.serpapi_client import ProviderError
from app.services.monitoring_service import check_watch, get_watch_by_id, in_flight_count
from app.workers.morning_brief import send_morning_briefs
from app.workers.scheduler import scheduler_status, shutdown_scheduler, start_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
# Provider requests put API keys in query strings; never emit request URLs at INFO.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    validate_runtime_settings()
    init_db()
    if settings.scheduler_enabled:
        start_scheduler()
    logger.info("Nazar Rakho backend started (env=%s)", settings.app_env)
    yield
    shutdown_scheduler()


app = FastAPI(
    title="Nazar Rakho API",
    description=(
        "AI-powered web search and continuous monitoring for family and friends group chats, "
        "with sourced results, alerts, and group voting."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (auth.router, rooms.router, messages.router, watches.router, alerts.router, votes.router):
    app.include_router(router, prefix=API_PREFIX)
app.include_router(webhooks.router, prefix=API_PREFIX)


@app.exception_handler(ProviderError)
async def provider_error_handler(_request: Request, exc: ProviderError) -> JSONResponse:
    logger.warning("Provider error (%s): %s", exc.provider, exc.message)
    return JSONResponse(
        status_code=503,
        content={"detail": exc.message, "provider": exc.provider, "retryable": exc.retryable},
    )


@app.get("/", tags=["meta"])
def root() -> dict:
    return {
        "name": settings.app_name,
        "docs": "/docs",
        "health": f"{API_PREFIX}/health",
    }


@app.get(f"{API_PREFIX}/health", tags=["monitoring"])
def health(db: Session = Depends(get_db)) -> dict:
    database_ok = True
    try:
        db.execute(text("SELECT 1"))
    except Exception:  # pragma: no cover - defensive health reporting
        database_ok = False
    return {
        "status": "ok" if database_ok else "degraded",
        "app": settings.app_name,
        "environment": settings.app_env,
        "database": "ok" if database_ok else "error",
        "providers": {
            "serpapi": "configured" if settings.serpapi_configured else "missing_key",
            "you": "configured" if settings.you_configured else "missing_key",
            "nexconn": "configured" if settings.nexconn_configured else "missing_key",
            "llm": "configured" if settings.llm_configured else "missing_key",
            "lyzr": "configured" if settings.lyzr_configured else "disabled_or_missing_key",
            "band": "configured" if settings.band_configured else "disabled_or_missing_key",
        },
        "llm": {
            "provider": settings.resolved_llm_provider,
            "model": settings.effective_llm_model,
            "base_url": settings.effective_llm_base_url,
        },
        "scheduler": scheduler_status(),
    }


def require_internal(x_internal_token: str | None = Header(default=None)) -> None:
    if settings.internal_api_token:
        if not x_internal_token or not hmac.compare_digest(
            settings.internal_api_token, x_internal_token
        ):
            raise HTTPException(status_code=401, detail="Invalid internal token")
        return
    if settings.is_production:
        raise HTTPException(
            status_code=403,
            detail="Internal endpoints require INTERNAL_API_TOKEN in production",
        )


@app.get(
    f"{API_PREFIX}/internal/workers/status",
    tags=["monitoring"],
    dependencies=[Depends(require_internal)],
)
def worker_status() -> dict:
    return {
        **scheduler_status(),
        "in_flight_watches": in_flight_count(),
        "watch_interval_minutes": settings.watch_interval_minutes,
        "max_alerts_per_watch_per_day": settings.max_alerts_per_watch_per_day,
    }


@app.post(
    f"{API_PREFIX}/internal/watches/{{watch_id}}/check",
    tags=["monitoring"],
    dependencies=[Depends(require_internal)],
)
async def run_watch_check(watch_id: int, db: Session = Depends(get_db)) -> dict:
    watch = get_watch_by_id(db, watch_id)
    from app.services.monitoring_service import check_watch
    return {"watch_id": watch.id, **await check_watch(db, watch, force=True)}


@app.post(
    f"{API_PREFIX}/internal/morning-brief",
    tags=["monitoring"],
    dependencies=[Depends(require_internal)],
)
def trigger_morning_brief(language: str | None = None) -> dict:
    return send_morning_briefs(language=language or settings.brief_language)
