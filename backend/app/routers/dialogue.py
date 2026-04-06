"""
app/routers/dialogue.py — Stateful dialogue session endpoints (Phase 7).
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.dependencies import DbDep, CurrentUser
from app.schemas.common import NotImplementedResponse

router = APIRouter(prefix="/dialogue", tags=["dialogue"])


@router.post("/session", response_model=NotImplementedResponse)
async def create_dialogue_session(db: DbDep, user: CurrentUser):
    """Create a new dialogue session (Phase 7, Section 9)."""
    return NotImplementedResponse()


@router.post("/{session_id}/beats", response_model=NotImplementedResponse)
async def generate_subtext_beats(session_id: uuid.UUID, db: DbDep, user: CurrentUser):
    """Generate subtext beats for the dialogue scene (Phase 7)."""
    return NotImplementedResponse()


@router.post("/{session_id}/turn", response_model=NotImplementedResponse)
async def generate_next_turn(session_id: uuid.UUID, db: DbDep, user: CurrentUser):
    """Generate the next dialogue turn (Phase 7, Section 9)."""
    return NotImplementedResponse()


@router.post("/{session_id}/export-to-prose", response_model=NotImplementedResponse)
async def export_dialogue_to_prose(session_id: uuid.UUID, db: DbDep, user: CurrentUser):
    """Convert dialogue transcript to prose via Stage 3 (Phase 7, Section 19)."""
    return NotImplementedResponse()
