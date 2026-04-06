"""
app/schemas/character.py — Pydantic schemas for characters.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from app.schemas.common import ORMBase


class CharacterCreate(ORMBase):
    name: str = Field(..., min_length=1, max_length=200)
    bio: str | None = None
    data: dict = Field(default_factory=dict)


class CharacterUpdate(ORMBase):
    name: str | None = None
    bio: str | None = None
    data: dict | None = None


class CharacterRead(ORMBase):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    bio: str | None
    data: dict
    thread_ids: list
    last_mentioned_chapter: int | None
    version: int
    created_at: datetime
    updated_at: datetime


class CharacterDeepenRequest(ORMBase):
    """Request body for POST /characters/{id}/deepen."""
    focus: str | None = Field(
        None, description="Optional focus area: 'backstory', 'motivation', 'voice'"
    )
