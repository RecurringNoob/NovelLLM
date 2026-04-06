"""
app/schemas/world.py — Pydantic schemas for worldbuilding entities.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.common import ORMBase


# ── Location ──────────────────────────────────────────────────────
class LocationCreate(ORMBase):
    name: str = Field(..., min_length=1)
    data: dict = Field(default_factory=dict)


class LocationRead(ORMBase):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    data: dict
    last_mentioned_chapter: int | None
    version: int


# ── PlotThread ────────────────────────────────────────────────────
class PlotThreadCreate(ORMBase):
    title: str = Field(..., min_length=1)
    description: str | None = None
    status: Literal["active", "dormant", "resolved"] = "active"


class PlotThreadUpdate(ORMBase):
    title: str | None = None
    description: str | None = None
    status: Literal["active", "dormant", "resolved"] | None = None


class PlotThreadRead(ORMBase):
    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    description: str | None
    status: str
    last_mentioned_chapter: int | None
    version: int
    # Warning: True if active and not mentioned in last 3 chapters
    stale_warning: bool = False


# ── Timeline ──────────────────────────────────────────────────────
class TimelineCellCreate(ORMBase):
    chapter_number: int = Field(..., ge=1)
    plotline_id: uuid.UUID
    scene_title: str | None = None
    scene_summary: str | None = None
    tension_score: int | None = Field(None, ge=1, le=10)
    position: int = 0


class TimelineCellRead(ORMBase):
    id: uuid.UUID
    project_id: uuid.UUID
    chapter_number: int
    plotline_id: uuid.UUID
    scene_title: str | None
    scene_summary: str | None
    tension_score: int | None
    position: int


# ── Template ──────────────────────────────────────────────────────
class ApplyTemplateRequest(ORMBase):
    template: Literal[
        "save_the_cat", "hero_journey", "three_act", "seven_point", "snowflake"
    ]
    chapter_count: int = Field(default=30, ge=5, le=200)
