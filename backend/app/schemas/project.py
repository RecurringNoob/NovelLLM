"""
app/schemas/project.py — Pydantic request/response models for projects and series.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.common import ORMBase


# ── Settings sub-schema ───────────────────────────────────────────
class ProjectSettings(ORMBase):
    tone: str | None = None
    pov: str | None = None
    auto_consistency: bool = True
    writing_mode: Literal["assist", "co-write", "auto"] = "co-write"
    maturity_level: Literal["general", "mature", "explicit"] = "general"
    tone_ceiling: str | None = None
    cost_budget_cents: int = 500


# ── Project ───────────────────────────────────────────────────────
class ProjectCreate(ORMBase):
    title: str = Field(..., min_length=1, max_length=500)
    genre: str | None = None
    premise: str | None = None
    series_id: uuid.UUID | None = None
    settings: ProjectSettings = Field(default_factory=ProjectSettings)


class ProjectUpdate(ORMBase):
    title: str | None = Field(None, min_length=1, max_length=500)
    genre: str | None = None
    premise: str | None = None
    settings: ProjectSettings | None = None
    cost_hard_limit_enabled: bool | None = None


class ProjectRead(ORMBase):
    id: uuid.UUID
    user_id: uuid.UUID | None
    series_id: uuid.UUID | None
    title: str
    genre: str | None
    premise: str | None
    settings: dict
    cost_spent_cents: int
    cost_hard_limit_enabled: bool
    created_at: datetime
    updated_at: datetime


class ProjectCostRead(ORMBase):
    project_id: uuid.UUID
    spent_cents: int
    budget_cents: int | None
    pct: float | None
    hard_limit_enabled: bool


# ── Series ────────────────────────────────────────────────────────
class SeriesCreate(ORMBase):
    title: str = Field(..., min_length=1)
    description: str | None = None


class SeriesRead(ORMBase):
    id: uuid.UUID
    title: str
    description: str | None
    book_order: list
    created_at: datetime
