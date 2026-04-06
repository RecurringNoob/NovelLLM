"""
app/schemas/chapter.py — Pydantic schemas for chapters and related entities.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from app.schemas.common import ORMBase


class ChapterCreate(ORMBase):
    chapter_number: int = Field(..., ge=1)
    title: str | None = None
    summary: str | None = None


class ChapterUpdate(ORMBase):
    title: str | None = None
    summary: str | None = None
    content: str | None = None


class ChapterRead(ORMBase):
    id: uuid.UUID
    project_id: uuid.UUID
    chapter_number: int
    title: str | None
    summary: str | None
    word_count: int | None
    needs_revalidation: bool
    created_at: datetime
    updated_at: datetime


class ChapterReadFull(ChapterRead):
    """Includes prose content — used by the chapter editor."""
    content: str | None


class ChapterStateSnapshotRead(ORMBase):
    project_id: uuid.UUID
    chapter_number: int
    current_location_id: uuid.UUID | None
    party_status: dict
    known_secrets: dict
    false_beliefs: dict
    false_belief_resolutions: dict
    world_conditions: dict


# ── Generation job request ────────────────────────────────────────
class GenerationRequest(ORMBase):
    project_id: uuid.UUID
    chapter_number: int
    intent: dict = Field(
        default_factory=dict,
        description="Stage 0 intent fields: tone_override, pov_character, "
                    "special_instructions, returning_entities, writing_mode",
    )


class GenerationJobResponse(ORMBase):
    job_id: uuid.UUID
    status: str = "queued"


class AutocompleteRequest(ORMBase):
    project_id: uuid.UUID
    chapter_number: int
    preceding_text: str = Field(..., max_length=5000)


class ContinueFromHereRequest(ORMBase):
    project_id: uuid.UUID
    chapter_number: int
    job_id: uuid.UUID
    checkpoint_num: int
    user_written_passage: str = Field(..., min_length=10)
    remaining_beats: list[dict] = Field(default_factory=list)


# ── Auto-fix ──────────────────────────────────────────────────────
class AutoFixWarningRequest(ORMBase):
    warning_index: int = Field(..., ge=0)


class AutoFixWarningResponse(ORMBase):
    original: str
    fixed: str
    diff: list[dict]
    paragraph_index: int


# ── Reorder ───────────────────────────────────────────────────────
class ReorderChaptersRequest(ORMBase):
    new_order: list[int] = Field(..., min_length=1)


class ReorderChaptersResponse(ORMBase):
    affected_from: int
    message: str


# ── Bible sync ────────────────────────────────────────────────────
class Range(ORMBase):
    from_: int = Field(..., alias="from")
    to: int


class BibleSyncRequest(ORMBase):
    changed_ranges: list[Range]
