"""
app/routers/bible.py — Story Bible management endpoints.

Phase 2 implements:
  - GET  /projects/{id}/pending-updates    list pending updates
  - POST /pending-updates/{id}/accept      OCC-safe accept
  - POST /pending-updates/{id}/reject      reject
  - PUT  /pending-updates/{id}/edit-and-accept  edit then accept (three-way merge)
  - POST /bible/rollback                   revert to event
  - POST /projects/{id}/stage5             manually trigger Stage 5 on existing prose

Style profiles remain stubbed — Phase 7.
"""
from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select, func

from app.core.exceptions import VersionConflictError, EntityNotFoundError
from app.dependencies import DbDep, CurrentUser
from app.models.bible import BibleEvent, PendingBibleUpdate
from app.models.chapter import Chapter
from app.schemas.bible import (
    AcceptPendingUpdateRequest,
    BibleRollbackRequest,
    EditAndAcceptRequest,
    PendingBibleUpdateRead,
    PromptRollbackRequest,
)
from app.schemas.common import NotImplementedResponse
from app.services.bible_service import (
    apply_pending_update,
    reject_pending_update as svc_reject,
    rollback_bible_to_event,
)
from app.services.notification_service import notify_pending_badge
from app.services.stage5_service import run_stage5
from app.services.bible_service import load_chapter_snapshot

router = APIRouter(tags=["bible"])


# ──────────────────────────────────────────────────────────────────
# Pending Bible Updates
# ──────────────────────────────────────────────────────────────────

@router.get(
    "/projects/{project_id}/pending-updates",
    response_model=list[PendingBibleUpdateRead],
)
async def list_pending_updates(
    project_id: uuid.UUID,
    db: DbDep,
    user: CurrentUser,
    status_filter: Literal["pending", "accepted", "rejected", "edited", "all"] = Query(
        "pending", alias="status"
    ),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """
    List bible updates for the Notification Center.
    Defaults to status=pending (unreviewed AI proposals).
    """
    q = select(PendingBibleUpdate).where(PendingBibleUpdate.project_id == project_id)
    if status_filter != "all":
        q = q.where(PendingBibleUpdate.status == status_filter)
    q = q.order_by(PendingBibleUpdate.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(q)
    return result.scalars().all()


@router.post(
    "/pending-updates/{update_id}/accept",
    response_model=PendingBibleUpdateRead,
)
async def accept_pending_update(
    update_id: uuid.UUID,
    db: DbDep,
    user: CurrentUser,
):
    """
    OCC-safe accept of a pending bible update (Section 18).
    Returns 409 with three-way merge payload on version conflict.
    """
    try:
        pending = await apply_pending_update(db, update_id)
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except VersionConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "version_conflict",
                "entity_id": str(exc.entity_id),
                "ai_saw_version": exc.ai_saw_version,
                "current_version": exc.current_version,
                "ai_changes": exc.ai_changes,
                "message": "Entity was modified since AI proposed this change. "
                           "Review the three-way merge.",
            },
        )
    await notify_pending_badge(db, pending.project_id)
    return pending


@router.post(
    "/pending-updates/{update_id}/reject",
    response_model=PendingBibleUpdateRead,
)
async def reject_pending_update(
    update_id: uuid.UUID,
    db: DbDep,
    user: CurrentUser,
):
    """Reject a pending bible update."""
    try:
        pending = await svc_reject(db, update_id)
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    await notify_pending_badge(db, pending.project_id)
    return pending


@router.put(
    "/pending-updates/{update_id}/edit-and-accept",
    response_model=PendingBibleUpdateRead,
)
async def edit_and_accept_pending_update(
    update_id: uuid.UUID,
    body: EditAndAcceptRequest,
    db: DbDep,
    user: CurrentUser,
):
    """
    User edits AI proposed changes then accepts (three-way merge resolution).
    Returns 409 on version conflict — same payload as plain accept.
    """
    try:
        pending = await apply_pending_update(db, update_id, edited_value=body.edited_value)
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except VersionConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "version_conflict",
                "entity_id": str(exc.entity_id),
                "ai_saw_version": exc.ai_saw_version,
                "current_version": exc.current_version,
                "ai_changes": exc.ai_changes,
            },
        )
    await notify_pending_badge(db, pending.project_id)
    return pending


# ──────────────────────────────────────────────────────────────────
# Bible Events (read-only log)
# ──────────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/bible-events")
async def list_bible_events(
    project_id: uuid.UUID,
    db: DbDep,
    user: CurrentUser,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Return the immutable bible event log for a project (event sourcing audit trail)."""
    result = await db.execute(
        select(BibleEvent)
        .where(BibleEvent.project_id == project_id)
        .order_by(BibleEvent.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    events = result.scalars().all()
    return [
        {
            "id": str(e.id),
            "chapter_number": e.chapter_number,
            "source": e.source,
            "entity_type": e.entity_type,
            "entity_id": str(e.entity_id) if e.entity_id else None,
            "changes": e.changes,
            "created_at": e.created_at.isoformat(),
        }
        for e in events
    ]


# ──────────────────────────────────────────────────────────────────
# Bible Rollback
# ──────────────────────────────────────────────────────────────────

@router.post("/bible/rollback")
async def rollback_bible(
    body: BibleRollbackRequest,
    db: DbDep,
    user: CurrentUser,
):
    """
    Roll back story bible to the snapshot captured at a specific event.
    Writes a compensating BibleEvent so the audit trail stays intact.
    """
    try:
        result = await rollback_bible_to_event(
            db,
            project_id=body.project_id,
            to_event_id=body.to_event_id,
        )
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return result


# ──────────────────────────────────────────────────────────────────
# Manual Stage 5 trigger (useful for testing / re-extraction)
# ──────────────────────────────────────────────────────────────────

@router.post("/projects/{project_id}/chapters/{chapter_number}/stage5")
async def trigger_stage5(
    project_id: uuid.UUID,
    chapter_number: int,
    db: DbDep,
    user: CurrentUser,
):
    """
    Manually re-run Stage 5 Delta Extraction on an existing chapter's prose.
    Useful during dev / testing without a full generation job.
    """
    # Load chapter
    result = await db.execute(
        select(Chapter).where(
            Chapter.project_id == project_id,
            Chapter.chapter_number == chapter_number,
        )
    )
    chapter = result.scalar_one_or_none()
    if chapter is None:
        raise HTTPException(status_code=404, detail="Chapter not found")
    if not chapter.content:
        raise HTTPException(status_code=422, detail="Chapter has no prose content yet")

    # Load prior snapshot
    prior_snap = await load_chapter_snapshot(db, project_id, chapter_number - 1)
    prior_dict = {
        "party_status": prior_snap.party_status if prior_snap else {},
        "known_secrets": prior_snap.known_secrets if prior_snap else {},
        "false_beliefs": prior_snap.false_beliefs if prior_snap else {},
        "false_belief_resolutions": prior_snap.false_belief_resolutions if prior_snap else {},
        "world_conditions": prior_snap.world_conditions if prior_snap else {},
    }

    import uuid as _uuid
    job_id = _uuid.uuid4()
    delta = await run_stage5(
        db,
        project_id=project_id,
        chapter_number=chapter_number,
        prose=chapter.content,
        prior_snapshot=prior_dict,
        job_id=job_id,
        maturity_level="general",
    )

    # Notify badge after pending updates written
    await notify_pending_badge(db, project_id)

    return {
        "job_id": str(job_id),
        "delta_summary": {
            "bible_additions": len(delta.get("bible_additions", [])),
            "plot_threads_opened": delta.get("plot_threads_opened", []),
            "plot_threads_closed": delta.get("plot_threads_closed", []),
            "false_beliefs_resolved_count": sum(
                len(v) for v in delta.get("false_beliefs_resolved", {}).values()
            ),
            "false_beliefs_introduced_count": sum(
                len(v) for v in delta.get("false_beliefs_introduced", {}).values()
            ),
        },
    }


# ──────────────────────────────────────────────────────────────────
# Chapter State Snapshots
# ──────────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/chapters/{chapter_number}/snapshot")
async def get_chapter_snapshot(
    project_id: uuid.UUID,
    chapter_number: int,
    db: DbDep,
    user: CurrentUser,
):
    """Return the narrative state snapshot at the end of a chapter."""
    snap = await load_chapter_snapshot(db, project_id, chapter_number)
    if snap is None:
        raise HTTPException(status_code=404, detail="Snapshot not yet generated for this chapter")
    return {
        "project_id": str(snap.project_id),
        "chapter_number": snap.chapter_number,
        "party_status": snap.party_status,
        "known_secrets": snap.known_secrets,
        "false_beliefs": snap.false_beliefs,
        "false_belief_resolutions": snap.false_belief_resolutions,
        "world_conditions": snap.world_conditions,
    }


# ──────────────────────────────────────────────────────────────────
# Style Profiles (Phase 7 stubs)
# ──────────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/style-profiles", response_model=NotImplementedResponse)
async def list_style_profiles(project_id: uuid.UUID, db: DbDep, user: CurrentUser):
    """List style profiles for a project (Phase 7)."""
    return NotImplementedResponse()


@router.post("/projects/{project_id}/style-profiles", response_model=NotImplementedResponse)
async def create_style_profile(project_id: uuid.UUID, db: DbDep, user: CurrentUser):
    """Create a style profile (Phase 7)."""
    return NotImplementedResponse()


@router.post(
    "/projects/{project_id}/style-profiles/{profile_id}/activate",
    response_model=NotImplementedResponse,
)
async def activate_style_profile(
    project_id: uuid.UUID, profile_id: uuid.UUID, db: DbDep, user: CurrentUser
):
    """Set a style profile as active (Phase 7)."""
    return NotImplementedResponse()
