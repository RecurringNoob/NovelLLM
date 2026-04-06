"""
app/routers/search.py — Semantic vector search endpoint (Phase 8).
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Query

from app.dependencies import DbDep, CurrentUser
from app.schemas.common import NotImplementedResponse

router = APIRouter(prefix="/projects/{project_id}/search", tags=["search"])


@router.get("", response_model=NotImplementedResponse)
async def semantic_search(
    project_id: uuid.UUID,
    q: str = Query(..., min_length=2, description="Search query"),
    limit: int = Query(5, ge=1, le=20),
    db: DbDep = ...,
    user: CurrentUser = ...,
):
    """
    pgvector semantic search across chapter summaries (Phase 8, Section 16).
    Embeds query with text-embedding-004, orders by cosine similarity.
    """
    return NotImplementedResponse()
