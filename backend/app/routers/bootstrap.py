"""
app/routers/bootstrap.py — Cold-start bootstrapping endpoints (Phase 7, Section 24).
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.dependencies import DbDep, CurrentUser
from app.schemas.common import NotImplementedResponse

router = APIRouter(prefix="/bootstrap", tags=["bootstrap"])


class IdeaSeedRequest(BaseModel):
    seed: str = Field(..., min_length=5, max_length=500)


class PremiseRefinementRequest(BaseModel):
    premise: str
    genre: str | None = None
    themes: list[str] = Field(default_factory=list)
    suggested_maturity_level: str | None = None


class CharactersBootstrapRequest(BaseModel):
    count: int = Field(default=3, ge=1, le=10)
    archetype_hints: list[str] = Field(default_factory=list)


class OutlineBootstrapRequest(BaseModel):
    structure_template: str = "save_the_cat"
    chapter_count: int = Field(default=30, ge=5, le=200)


@router.post("/idea", response_model=NotImplementedResponse)
async def expand_seed_idea(body: IdeaSeedRequest, db: DbDep, user: CurrentUser):
    """
    Step 1: Expand a seed idea into premise, genre, themes, and maturity level suggestion.
    (Phase 7, Section 24)
    """
    return NotImplementedResponse()


@router.put("/{project_id}/premise", response_model=NotImplementedResponse)
async def refine_premise(project_id: uuid.UUID, body: PremiseRefinementRequest, db: DbDep, user: CurrentUser):
    """Step 2: User edits and confirms premise (Phase 7)."""
    return NotImplementedResponse()


@router.post("/{project_id}/characters", response_model=NotImplementedResponse)
async def bootstrap_characters(project_id: uuid.UUID, body: CharactersBootstrapRequest, db: DbDep, user: CurrentUser):
    """Step 3: Generate initial characters from archetype hints (Phase 7)."""
    return NotImplementedResponse()


@router.post("/{project_id}/outline", response_model=NotImplementedResponse)
async def bootstrap_outline(project_id: uuid.UUID, body: OutlineBootstrapRequest, db: DbDep, user: CurrentUser):
    """Step 4: Generate outline scaffold from plot template (Phase 7)."""
    return NotImplementedResponse()
