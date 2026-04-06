"""
app/schemas/bible.py — Pydantic schemas for the Story Bible system.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.common import ORMBase


# ── Pending Bible Update ──────────────────────────────────────────
class PendingBibleUpdateRead(ORMBase):
    id: uuid.UUID
    project_id: uuid.UUID
    chapter_number: int | None
    entity_type: str | None
    entity_id: uuid.UUID | None
    proposed_changes: dict
    entity_version_at_proposal: int | None
    status: str
    source: str | None
    created_at: datetime


class AcceptPendingUpdateRequest(ORMBase):
    """Accept without editing — uses proposed_changes as-is."""
    pass


class EditAndAcceptRequest(ORMBase):
    """Apply user-edited version of proposed_changes."""
    edited_value: dict = Field(..., description="User-edited replacement for proposed_changes")


# ── Bible rollback ────────────────────────────────────────────────
class BibleRollbackRequest(ORMBase):
    to_event_id: uuid.UUID = Field(..., description="Roll back to (and including) this event")


# ── Prompt templates ──────────────────────────────────────────────
class PromptTemplateRead(ORMBase):
    id: uuid.UUID
    name: str
    stage: str
    version: int
    is_active: bool
    description: str | None
    created_at: datetime


class PromptRollbackRequest(ORMBase):
    to_version: int = Field(..., ge=1)


# ── Generation logs ───────────────────────────────────────────────
class GenerationLogRead(ORMBase):
    id: uuid.UUID
    job_id: uuid.UUID | None
    chapter_number: int | None
    stage: str | None
    model: str | None
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int | None
    safety_blocked: bool
    blocked_twice: bool
    ner_guard_triggered: bool
    maturity_level: str | None
    scene_intensity: str | None
    created_at: datetime
