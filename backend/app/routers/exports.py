"""
app/routers/exports.py — Export endpoints (Phase 8).
"""
from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Query

from app.dependencies import DbDep, CurrentUser
from app.schemas.common import NotImplementedResponse

router = APIRouter(prefix="/projects/{project_id}/export", tags=["exports"])


@router.get("", response_model=NotImplementedResponse)
async def export_project(
    project_id: uuid.UUID,
    format: Literal["md", "pdf", "docx", "shunn", "epub3"] = Query("md"),
    db: DbDep = ...,
    user: CurrentUser = ...,
):
    """
    Export project to the requested format (Phase 8, Section 22).
    Formats: Markdown, Word (.docx), PDF (WeasyPrint), Shunn Manuscript, EPUB3.
    """
    return NotImplementedResponse()
