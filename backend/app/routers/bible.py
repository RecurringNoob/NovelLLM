"""
app/routers/bible.py — Story Bible management endpoints.
Pending updates, rollback, prompt templates — Phase 2+.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.dependencies import DbDep, CurrentUser
from app.schemas.bible import (
    PendingBibleUpdateRead,
    AcceptPendingUpdateRequest,
    EditAndAcceptRequest,
    BibleRollbackRequest,
    PromptRollbackRequest,
)
from app.schemas.common import NotImplementedResponse

router = APIRouter(tags=["bible"])


# ── Pending updates ────────────────────────────────────────────────
@router.get("/projects/{project_id}/pending-updates", response_model=NotImplementedResponse)
async def list_pending_updates(project_id: uuid.UUID, db: DbDep, user: CurrentUser):
    """List pending bible updates for the Notification Center (Phase 2)."""
    return NotImplementedResponse()


@router.post("/pending-updates/{update_id}/accept", response_model=NotImplementedResponse)
async def accept_pending_update(update_id: uuid.UUID, db: DbDep, user: CurrentUser):
    """OCC-safe accept of a pending bible update (Phase 2, Section 18)."""
    return NotImplementedResponse()


@router.post("/pending-updates/{update_id}/reject", response_model=NotImplementedResponse)
async def reject_pending_update(update_id: uuid.UUID, db: DbDep, user: CurrentUser):
    """Reject a pending bible update (Phase 2)."""
    return NotImplementedResponse()


@router.put("/pending-updates/{update_id}/edit-and-accept", response_model=NotImplementedResponse)
async def edit_and_accept_pending_update(update_id: uuid.UUID, body: EditAndAcceptRequest, db: DbDep, user: CurrentUser):
    """User edits proposed changes then accepts (Phase 2, Section 18)."""
    return NotImplementedResponse()


# ── Bible rollback ─────────────────────────────────────────────────
@router.post("/bible/rollback", response_model=NotImplementedResponse)
async def rollback_bible(body: BibleRollbackRequest, db: DbDep, user: CurrentUser):
    """Roll back story bible to a specific event (Phase 2)."""
    return NotImplementedResponse()


# ── Style profiles ─────────────────────────────────────────────────
@router.get("/projects/{project_id}/style-profiles", response_model=NotImplementedResponse)
async def list_style_profiles(project_id: uuid.UUID, db: DbDep, user: CurrentUser):
    """List style profiles for a project (Phase 7)."""
    return NotImplementedResponse()


@router.post("/projects/{project_id}/style-profiles", response_model=NotImplementedResponse)
async def create_style_profile(project_id: uuid.UUID, db: DbDep, user: CurrentUser):
    """Create a style profile (Phase 7)."""
    return NotImplementedResponse()


@router.post("/projects/{project_id}/style-profiles/{profile_id}/activate", response_model=NotImplementedResponse)
async def activate_style_profile(project_id: uuid.UUID, profile_id: uuid.UUID, db: DbDep, user: CurrentUser):
    """Set a style profile as active (Phase 7)."""
    return NotImplementedResponse()
