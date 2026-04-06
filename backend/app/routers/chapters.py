"""
app/routers/chapters.py — Chapter CRUD + generation-related stubs.
Phase 1: CRUD implemented. Generation, autocomplete, auto-fix → Phase 1 pipeline stubs.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.dependencies import DbDep, CurrentUser
from app.models.chapter import Chapter
from app.schemas.chapter import (
    ChapterCreate,
    ChapterRead,
    ChapterReadFull,
    ChapterUpdate,
    AutoFixWarningRequest,
    AutoFixWarningResponse,
    BibleSyncRequest,
    ReorderChaptersRequest,
    ReorderChaptersResponse,
)
from app.schemas.common import NotImplementedResponse

router = APIRouter(prefix="/chapters", tags=["chapters"])


@router.post("", response_model=ChapterRead, status_code=status.HTTP_201_CREATED)
async def create_chapter(body: ChapterCreate, project_id: uuid.UUID, db: DbDep, user: CurrentUser):
    """Manually create a chapter record (without AI generation)."""
    chapter = Chapter(
        project_id=project_id,
        chapter_number=body.chapter_number,
        title=body.title,
        summary=body.summary,
    )
    db.add(chapter)
    await db.flush()
    await db.refresh(chapter)
    return chapter


@router.get("/{chapter_id}", response_model=ChapterReadFull)
async def get_chapter(chapter_id: uuid.UUID, db: DbDep, user: CurrentUser):
    """
    Fetch a chapter. If needs_revalidation=True, enqueues lazy
    Stage 5 + Stage 6 jobs (Phase 3/4) and returns the chapter immediately.
    """
    chapter = await db.get(Chapter, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    # Phase 3+: if chapter.needs_revalidation → enqueue_stage5_replay + enqueue_stage6
    return chapter


@router.patch("/{chapter_id}", response_model=ChapterRead)
async def update_chapter(chapter_id: uuid.UUID, body: ChapterUpdate, db: DbDep, user: CurrentUser):
    chapter = await db.get(Chapter, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(chapter, k, v)
    if body.content:
        chapter.word_count = len(body.content.split())
    await db.flush()
    await db.refresh(chapter)
    return chapter


@router.delete("/{chapter_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chapter(chapter_id: uuid.UUID, db: DbDep, user: CurrentUser):
    chapter = await db.get(Chapter, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    await db.delete(chapter)


@router.post("/{chapter_id}/sync-bible-from-prose", response_model=NotImplementedResponse)
async def sync_bible_from_prose(chapter_id: uuid.UUID, body: BibleSyncRequest, db: DbDep, user: CurrentUser):
    """Diff-based prose-to-bible sync (Phase 3, Section 30)."""
    return NotImplementedResponse()


@router.post("/{chapter_id}/auto-fix-warning", response_model=NotImplementedResponse)
async def auto_fix_warning(chapter_id: uuid.UUID, body: AutoFixWarningRequest, db: DbDep, user: CurrentUser):
    """Stage 6 auto-fix for a single consistency warning (Phase 4, Section 33)."""
    return NotImplementedResponse()
