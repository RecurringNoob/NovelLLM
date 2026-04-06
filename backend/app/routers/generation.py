"""
app/routers/generation.py — AI generation pipeline endpoints.
Phase 1: All stubs — job IDs returned immediately.
Full pipeline logic implemented in Phases 1–4.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.dependencies import DbDep, CurrentUser
from app.schemas.chapter import (
    GenerationRequest,
    GenerationJobResponse,
    AutocompleteRequest,
    ContinueFromHereRequest,
)
from app.schemas.common import NotImplementedResponse

router = APIRouter(prefix="/chapters", tags=["generation"])


@router.post("/generate", response_model=GenerationJobResponse)
async def generate_chapter(body: GenerationRequest, db: DbDep, user: CurrentUser):
    """
    Enqueue a full 7-stage generation job.
    Returns job_id immediately; progress via GET /api/jobs/{job_id}/stream (SSE).
    Phase 1: Returns stub job_id.
    """
    return GenerationJobResponse(job_id=uuid.uuid4(), status="queued_stub")


@router.post("/autocomplete", response_model=NotImplementedResponse)
async def autocomplete(body: AutocompleteRequest, db: DbDep, user: CurrentUser):
    """
    Copilot next-paragraph completion (Phase 6, Section 14).
    Target: first token < 1s. Bypasses Stages 0–2.
    """
    return NotImplementedResponse()


@router.post("/rerun-from-stage", response_model=GenerationJobResponse)
async def rerun_from_stage(db: DbDep, user: CurrentUser):
    """
    Partial pipeline re-run from a specified stage (Phase 3).
    Used when user edits beats and wants Stage 3 to re-run.
    """
    return GenerationJobResponse(job_id=uuid.uuid4(), status="queued_stub")


@router.post("/continue-from-here", response_model=GenerationJobResponse)
async def continue_from_here(body: ContinueFromHereRequest, db: DbDep, user: CurrentUser):
    """
    Resume generation after a safety block using user-written passage as fixed context.
    (Phase 4, Section 37 — 'Continue from here' recovery path.)
    """
    return GenerationJobResponse(job_id=uuid.uuid4(), status="queued_stub")


# ── SSE job stream ─────────────────────────────────────────────────
jobs_router = APIRouter(prefix="/jobs", tags=["generation"])


@jobs_router.get("/{job_id}/stream")
async def stream_job(job_id: uuid.UUID, db: DbDep, user: CurrentUser):
    """
    SSE endpoint streaming pipeline stage events for a generation job.
    Events: beat, prose_chunk, checkpoint, prose_done, safety_block,
            consistency_warnings, revalidation_complete.
    Phase 1: Returns a stub 'not_implemented' SSE event.
    """
    async def stub_generator():
        yield f"event: not_implemented\ndata: {{\"phase\": 1, \"job_id\": \"{job_id}\"}}\n\n"

    return StreamingResponse(stub_generator(), media_type="text/event-stream")
