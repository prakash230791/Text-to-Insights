"""
Module 8 — API Gateway  (api/main.py)

FastAPI application entry point. Registers all routes, middleware,
rate limiting, and startup/shutdown lifecycle events.

Endpoints:
  POST /query              — Submit a natural language query
  GET  /query/history      — Past queries for authenticated user
  GET  /schema/tables      — Browse registered tables
  GET  /schema/values/{t}  — Value mappings for a table
  GET  /audit/log          — Full audit trail (admin only)
  GET  /health             — System health check
  POST /auth/token         — Exchange credentials for JWT
"""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

import ollama
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text

from api.auth import router as auth_router
from api.middleware.audit_logger import init_audit_db
from api.middleware.rate_limiter import limiter
from api.routes.audit import router as audit_router
from api.routes.query import router as query_router
from api.routes.schema import router as schema_router
from config.settings import get_settings
from registry.schema_db import SchemaDB

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)
cfg = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DBs and warm the pipeline on startup."""
    logger.info("Text-to-Insights API starting up")
    db = SchemaDB(cfg.registry_db_url)
    db.init_db()
    init_audit_db()
    logger.info("Databases initialized")
    yield
    logger.info("Text-to-Insights API shutting down")


app = FastAPI(
    title="Text-to-Insights API",
    description=(
        "Enterprise natural-language query system for telecom OSS/BSS metrics. "
        "Zero external API spend — 100% on-premise with Ollama SLMs."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── Rate limiting ──────────────────────────────────────────────────────────────
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def _rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": f"Rate limit exceeded. Max {cfg.rate_limit_per_minute} requests/minute."},
    )


# ── CORS (adjust origins for production) ──────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501"],  # Streamlit dev origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request timing middleware ──────────────────────────────────────────────────
@app.middleware("http")
async def _add_timing_header(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000
    response.headers["X-Response-Time-Ms"] = f"{elapsed_ms:.1f}"
    return response


# ── Routers ────────────────────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(query_router)
app.include_router(schema_router)
app.include_router(audit_router)


# ── Health check ───────────────────────────────────────────────────────────────
@app.get("/health", tags=["ops"], summary="System health check")
async def health_check() -> dict:
    """Returns status of all system components: Registry DB, Metrics DB, Ollama."""
    status_out: dict = {"status": "ok", "components": {}}

    # Registry DB
    try:
        db = SchemaDB(cfg.registry_db_url)
        with db.session() as sess:
            sess.execute(text("SELECT 1"))
        status_out["components"]["registry_db"] = "ok"
    except Exception as exc:
        status_out["components"]["registry_db"] = f"error: {exc}"
        status_out["status"] = "degraded"

    # Metrics DB
    try:
        from sqlalchemy import create_engine
        engine = create_engine(cfg.metrics_db_url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        status_out["components"]["metrics_db"] = "ok"
    except Exception as exc:
        status_out["components"]["metrics_db"] = f"error: {exc}"
        status_out["status"] = "degraded"

    # Ollama
    try:
        client = ollama.Client(host=cfg.ollama_base_url)
        models = client.list()
        available = [m["model"] for m in models.get("models", [])]
        status_out["components"]["ollama"] = {
            "status": "ok",
            "available_models": available,
            "sql_model_ready": cfg.ollama_sql_model in " ".join(available),
            "report_model_ready": cfg.ollama_report_model in " ".join(available),
        }
    except Exception as exc:
        status_out["components"]["ollama"] = f"error: {exc}"
        status_out["status"] = "degraded"

    return status_out


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host=cfg.api_host,
        port=cfg.api_port,
        reload=(cfg.app_env == "development"),
        log_level=cfg.log_level.lower(),
    )
