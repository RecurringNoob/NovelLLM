"""
app/routers/generation.py — AI generation pipeline endpoints.

Phase 2:
  - POST /chapters/generate     → creates GenerationJob DB record + enqueues to Redis
  - POST /chapters/continue-from-here → creates job with prepend_prose
  - GET  /jobs/{job_id}/stream  → SSE; polls job status from Redis/DB
  - POST /beats/{job_id}/confirm → user confirms beats before Stage 3 (co-write / assist)

Autocomplete and rerun-from-stage remain stubbed — Phase 6.
Full worker pipeline (Stages 0–6) implemented as the worker is wired up in Phase 1→4.
"""
from __future__ import annotations

import json
import uuid as _uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.core.exceptions import BudgetExceededError
from app.dependencies import DbDep, CurrentUser
from app.models.job import GenerationJob
from app.models.project import Project
from app.schemas.chapter import (
    AutocompleteRequest,
    ContinueFromHereRequest,
    GenerationJobResponse,
    GenerationRequest,
)
from app.schemas.common import NotImplementedResponse
from app.core.redis_client import get_redis_pool

router = APIRouter(prefix="/chapters", tags=["generation"])


async def _check_budget(project: Project) -> None:
    """Raise BudgetExceededError if hard cost limit is enabled and exhausted."""
    if not project.cost_hard_limit_enabled:
        return
    budget = project.settings.get("cost_budget_cents")
    if budget and project.cost_spent_cents >= budget:
        raise BudgetExceededError(
            spent_cents=project.cost_spent_cents,
            budget_cents=budget,
            project_id=str(project.id),
        )


@router.post("/generate", response_model=GenerationJobResponse)
async def generate_chapter(body: GenerationRequest, db: DbDep, user: CurrentUser):
    """
    Enqueue a full 7-stage generation job.

    Phase 2:
    - Performs hard budget check before enqueuing (Section 36).
    - Creates a GenerationJob DB record (status=queued).
    - Publishes job_id to Redis stream 'job_stream' for the worker pool.
    - Returns job_id immediately; caller polls GET /api/jobs/{id}/stream for SSE events.

    Worker pipeline (Stages 0–6) is wired in the background worker module (Phase 1+).
    """
    # Load project for budget check
    project = await db.get(Project, body.project_id)
    if not project or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        await _check_budget(project)
    except BudgetExceededError as exc:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "budget_exceeded",
                "message": "Generation blocked: project budget exhausted.",
                "spent_cents": exc.spent_cents,
                "budget_cents": exc.budget_cents,
                "action": "Increase budget in Project Settings or disable the hard limit.",
            },
        )

    # Create job record
    job = GenerationJob(
        project_id=body.project_id,
        chapter_number=body.chapter_number,
        status="queued",
        mode=body.intent.get("writing_mode", project.settings.get("writing_mode", "co-write")),
        maturity_level=project.settings.get("maturity_level", "general"),
        intent=body.intent,
    )
    db.add(job)
    await db.flush()
    await db.refresh(job)

    # Publish to Redis Streams (worker picks it up)
    try:
        redis = get_redis_pool()
        await redis.xadd(
            "job_stream",
            {
                "job_id": str(job.id),
                "project_id": str(body.project_id),
                "chapter_number": str(body.chapter_number),
                "intent": json.dumps(body.intent),
            },
        )
    except Exception:
        # Non-fatal for Phase 2 — worker polling will pick it up on next scan
        pass

    return GenerationJobResponse(job_id=job.id, status="queued")


@router.post("/autocomplete", response_model=NotImplementedResponse)
async def autocomplete(body: AutocompleteRequest, db: DbDep, user: CurrentUser):
    """Copilot next-paragraph completion (Phase 6, Section 14)."""
    return NotImplementedResponse()


@router.post("/rerun-from-stage", response_model=GenerationJobResponse)
async def rerun_from_stage(db: DbDep, user: CurrentUser):
    """Partial pipeline re-run from a specified stage (Phase 3)."""
    return GenerationJobResponse(job_id=_uuid.uuid4(), status="queued_stub")


@router.post("/continue-from-here", response_model=GenerationJobResponse)
async def continue_from_here(body: ContinueFromHereRequest, db: DbDep, user: CurrentUser):
    """
    Resume generation after a safety block using user-written passage as fixed context.
    (Section 37 — 'Continue from here' recovery path.)
    Phase 2: Creates the job record with prepend_prose.
    Full Stage 3 resume wired in Phase 4.
    """
    project = await db.get(Project, body.project_id)
    if not project or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    job = GenerationJob(
        project_id=body.project_id,
        chapter_number=body.chapter_number,
        status="queued",
        mode="continue_from_manual_write",
        maturity_level=project.settings.get("maturity_level", "general"),
        # Remaining beats are stored in the intent blob for the worker
        intent={
            "continue_from_checkpoint": body.checkpoint_num,
            "user_written_passage": body.user_written_passage,
            "remaining_beats": body.remaining_beats,
            "original_job_id": str(body.job_id),
        },
    )
    db.add(job)
    await db.flush()
    await db.refresh(job)

    try:
        redis = get_redis_pool()
        await redis.xadd(
            "job_stream",
            {
                "job_id": str(job.id),
                "project_id": str(body.project_id),
                "chapter_number": str(body.chapter_number),
                "mode": "continue_from_manual_write",
            },
        )
    except Exception:
        pass

    return GenerationJobResponse(job_id=job.id, status="queued")


# ── Beat confirmation (co-write / assist modes) ────────────────────
beats_router = APIRouter(prefix="/beats", tags=["generation"])


@beats_router.put("/{job_id}/confirm")
async def confirm_beats(
    job_id: _uuid.UUID,
    beats: list[dict],
    db: DbDep,
    user: CurrentUser,
):
    """
    User confirms (or edits) the Stage 2 beats before Stage 3 runs.
    Updates the job's beats field and sets status back to 'queued' for Stage 3.
    (TDD Section 6, Stage 2 'User Edit Gate'.)
    """
    result = await db.execute(
        select(GenerationJob).where(GenerationJob.id == job_id)
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Generation job not found")
    job.beats = beats
    job.status = "queued"  # Worker resumes from Stage 3
    await db.flush()

    try:
        redis = get_redis_pool()
        await redis.xadd(
            "job_stream",
            {"job_id": str(job_id), "resume_from_stage": "3"},
        )
    except Exception:
        pass

    return {"job_id": str(job_id), "status": "queued", "beats_confirmed": len(beats)}


# ── SSE job stream ─────────────────────────────────────────────────
jobs_router = APIRouter(prefix="/jobs", tags=["generation"])


@jobs_router.get("/{job_id}/stream")
async def stream_job(job_id: _uuid.UUID, db: DbDep, user: CurrentUser):
    """
    SSE endpoint polling job status and streaming pipeline events.

    Phase 2: Polls the GenerationJob DB record and streams status events.
    Phase 4: Connected to the full CheckpointedProseStream for real prose chunks.

    Events emitted:
      job_status  — { "status": "queued|running|done|failed|safety_blocked", "stage": "3" }
      beats       — Stage 2 beat list (for user edit gate)
      prose_done  — { "word_count": N }
      safety_block — { "checkpoint": N, "words_written": N, "recovery_options": [...] }
    """
    async def event_generator():
        import asyncio
        MAX_POLLS = 360  # 3 minutes at 0.5s intervals
        for _ in range(MAX_POLLS):
            result = await db.execute(
                select(GenerationJob).where(GenerationJob.id == job_id)
            )
            job = result.scalar_one_or_none()
            if job is None:
                yield f"event: error\ndata: {{\"message\": \"Job not found\"}}\n\n"
                return

            payload = json.dumps({
                "status": job.status,
                "stage": job.stage,
                "mode": job.mode,
            })
            yield f"event: job_status\ndata: {payload}\n\n"

            if job.status in ("done", "failed"):
                return
            if job.status == "safety_blocked":
                safety_payload = json.dumps({
                    "checkpoint": job.blocked_at_checkpoint,
                    "words_written": len((job.partial_prose or "").split()),
                    "message": "Content filter triggered. Prose saved up to last checkpoint.",
                    "recovery_options": ["rephrase_beats", "write_manually", "skip_scene"],
                })
                yield f"event: safety_block\ndata: {safety_payload}\n\n"
                return

            # Emit beats when Stage 2 is complete and awaiting user confirmation
            if job.beats and job.status == "queued" and job.stage == "2":
                beats_payload = json.dumps({"beats": job.beats, "job_id": str(job_id)})
                yield f"event: beats\ndata: {beats_payload}\n\n"

            await asyncio.sleep(0.5)

        yield f"event: timeout\ndata: {{\"message\": \"Stream timeout\"}}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
