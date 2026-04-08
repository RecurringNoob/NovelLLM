"""
app/schemas/bible.py — Pydantic schemas for the Story Bible system.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from app.schemas.common import ORMBase


# ── Pending Bible Update ──────────────────────────────────────────
class PendingBibleUpdateRead(ORMBase):
    id: uuid.UUID
    project_id: uuid.UUID
    chapter_number: int | None = None
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    proposed_changes: dict
    entity_version_at_proposal: int | None = None
    status: str
    source: str | None = None
    # Three-way merge support (v4)
    user_edited_value: dict | None = None
    created_at: datetime
    resolved_at: datetime | None = None


class AcceptPendingUpdateRequest(ORMBase):
    """Accept without editing — uses proposed_changes as-is."""
    pass


class EditAndAcceptRequest(ORMBase):
    """Apply user-edited version of proposed_changes (three-way merge resolution)."""
    edited_value: dict = Field(..., description="User-edited replacement for proposed_changes")


# ── Bible rollback ────────────────────────────────────────────────
class BibleRollbackRequest(ORMBase):
    project_id: uuid.UUID = Field(..., description="Project the event belongs to")
    to_event_id: uuid.UUID = Field(..., description="Roll back to the snapshot at this event")


# ── Prompt templates ──────────────────────────────────────────────
class PromptTemplateRead(ORMBase):
    id: uuid.UUID
    name: str
    stage: str
    version: int
    is_active: bool
    description: str | None = None
    created_at: datetime


class PromptRollbackRequest(ORMBase):
    to_version: int = Field(..., ge=1)


# ── Generation logs ───────────────────────────────────────────────
class GenerationLogRead(ORMBase):
    id: uuid.UUID
    job_id: uuid.UUID | None = None
    chapter_number: int | None = None
    stage: str | None = None
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None
    safety_blocked: bool
    blocked_twice: bool
    ner_guard_triggered: bool
    maturity_level: str | None = None
    scene_intensity: str | None = None
    created_at: datetime


# ── Stage 5 manual trigger response ──────────────────────────────
class Stage5TriggerResponse(ORMBase):
    job_id: str
    delta_summary: dict
