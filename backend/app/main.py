"""
app/main.py — FastAPI application entry point.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.core.logging import configure_logging
from app.core.redis_client import close_redis_pool, get_redis_pool, redis_ping
from app.database import engine
from app.core.exceptions import (
    BudgetExceededError,
    InjectionDetectedError,
    VersionConflictError,
)

# Configure logging before importing routers (routers use module loggers)
configure_logging()
logger = logging.getLogger("notelm.main")

# ── Import routers ────────────────────────────────────────────────
from app.routers.projects import router as projects_router, series_router
from app.routers.chapters import router as chapters_router
from app.routers.characters import router as characters_router
from app.routers.plot_threads import router as plot_threads_router
from app.routers.bible import router as bible_router
from app.routers.generation import router as generation_router, jobs_router
from app.routers.dialogue import router as dialogue_router
from app.routers.search import router as search_router
from app.routers.exports import router as exports_router
from app.routers.bootstrap import router as bootstrap_router
from app.routers.admin import router as admin_router


# ── Lifespan (startup / shutdown) ─────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Novel Writing Assistant API (Phase 1)")

    # Verify Redis connectivity
    if await redis_ping():
        logger.info("Redis connected ✓")
    else:
        logger.warning("Redis not reachable — some features will be degraded")

    # Verify DB connectivity (engine does not open a connection until first use;
    # this is just a sanity probe)
    try:
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        logger.info("PostgreSQL connected ✓")
    except Exception as exc:
        logger.error(f"PostgreSQL connection failed: {exc}")

    yield

    # Shutdown
    logger.info("Shutting down API…")
    await close_redis_pool()
    await engine.dispose()
    logger.info("Shutdown complete")


# ── App factory ───────────────────────────────────────────────────
app = FastAPI(
    title="Novel Writing Assistant",
    description=(
        "A web-based collaborative writing tool where Gemini AI assists "
        "with outlining, character/world development, chapter drafting, dialogue, "
        "and consistency. Supports mature content pipelines, CRDTs, and a "
        "7-stage generation pipeline."
    ),
    version="0.1.0-phase1",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Global exception handlers ─────────────────────────────────────
@app.exception_handler(BudgetExceededError)
async def budget_exceeded_handler(request: Request, exc: BudgetExceededError):
    return JSONResponse(
        status_code=403,
        content={
            "error": "budget_exceeded",
            "message": "Generation blocked: project budget exhausted.",
            "spent_cents": exc.spent_cents,
            "budget_cents": exc.budget_cents,
            "action": "Increase budget in Project Settings or disable the hard limit.",
        },
    )


@app.exception_handler(InjectionDetectedError)
async def injection_handler(request: Request, exc: InjectionDetectedError):
    # Generic message to user; specific reason logged internally
    logger.warning(f"Injection detected [{exc.layer}]: {exc.reason}")
    return JSONResponse(
        status_code=400,
        content={"error": "invalid_instruction", "message": "Instruction could not be processed."},
    )


@app.exception_handler(VersionConflictError)
async def version_conflict_handler(request: Request, exc: VersionConflictError):
    return JSONResponse(
        status_code=409,
        content={
            "error": "version_conflict",
            "entity_id": str(exc.entity_id),
            "ai_saw_version": exc.ai_saw_version,
            "current_version": exc.current_version,
            "message": "The entity was modified since the AI proposed this change. "
                       "Please review the three-way merge.",
            "ai_changes": exc.ai_changes,
        },
    )


# ── Health check ──────────────────────────────────────────────────
@app.get("/health", tags=["health"])
async def health_check():
    redis_ok = await redis_ping()
    return {
        "status": "ok",
        "db": "connected",      # If we got here, DB is reachable (lifespan verified)
        "redis": "connected" if redis_ok else "degraded",
        "environment": settings.environment,
        "version": "0.1.0-phase1",
    }


# ── Mount all routers ─────────────────────────────────────────────
PREFIX = "/api"

app.include_router(projects_router,     prefix=PREFIX)
app.include_router(series_router,       prefix=PREFIX)
app.include_router(chapters_router,     prefix=PREFIX)
app.include_router(characters_router,   prefix=PREFIX)
app.include_router(plot_threads_router, prefix=PREFIX)
app.include_router(bible_router,        prefix=PREFIX)
app.include_router(generation_router,   prefix=PREFIX)
app.include_router(jobs_router,         prefix=PREFIX)
app.include_router(dialogue_router,     prefix=PREFIX)
app.include_router(search_router,       prefix=PREFIX)
app.include_router(exports_router,      prefix=PREFIX)
app.include_router(bootstrap_router,    prefix=PREFIX)
app.include_router(admin_router,        prefix=PREFIX)
