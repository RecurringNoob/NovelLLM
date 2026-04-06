"""
app/routers/plot_threads.py — Plot thread CRUD endpoints.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.dependencies import DbDep, CurrentUser
from app.models.world import PlotThread
from app.schemas.world import PlotThreadCreate, PlotThreadRead, PlotThreadUpdate

router = APIRouter(prefix="/projects/{project_id}/plot-threads", tags=["plot_threads"])


@router.get("", response_model=list[PlotThreadRead])
async def list_plot_threads(project_id: uuid.UUID, db: DbDep, user: CurrentUser):
    """List all plot threads. Adds stale_warning=True if active and last mentioned 3+ chapters ago."""
    # NOTE: chapter_count requires a subquery; Phase 5 adds the full warning logic.
    result = await db.execute(
        select(PlotThread)
        .where(PlotThread.project_id == project_id)
        .order_by(PlotThread.status, PlotThread.title)
    )
    threads = result.scalars().all()
    # TODO Phase 5: compute stale_warning based on last_mentioned_chapter vs current max chapter
    return [PlotThreadRead.model_validate(t) for t in threads]


@router.post("", response_model=PlotThreadRead, status_code=status.HTTP_201_CREATED)
async def create_plot_thread(project_id: uuid.UUID, body: PlotThreadCreate, db: DbDep, user: CurrentUser):
    thread = PlotThread(
        project_id=project_id,
        title=body.title,
        description=body.description,
        status=body.status,
    )
    db.add(thread)
    await db.flush()
    await db.refresh(thread)
    return PlotThreadRead.model_validate(thread)


@router.get("/{thread_id}", response_model=PlotThreadRead)
async def get_plot_thread(project_id: uuid.UUID, thread_id: uuid.UUID, db: DbDep, user: CurrentUser):
    thread = await db.get(PlotThread, thread_id)
    if not thread or thread.project_id != project_id:
        raise HTTPException(status_code=404, detail="Plot thread not found")
    return PlotThreadRead.model_validate(thread)


@router.patch("/{thread_id}", response_model=PlotThreadRead)
async def update_plot_thread(project_id: uuid.UUID, thread_id: uuid.UUID, body: PlotThreadUpdate, db: DbDep, user: CurrentUser):
    thread = await db.get(PlotThread, thread_id)
    if not thread or thread.project_id != project_id:
        raise HTTPException(status_code=404, detail="Plot thread not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(thread, k, v)
    thread.version += 1
    await db.flush()
    await db.refresh(thread)
    return PlotThreadRead.model_validate(thread)


@router.delete("/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plot_thread(project_id: uuid.UUID, thread_id: uuid.UUID, db: DbDep, user: CurrentUser):
    thread = await db.get(PlotThread, thread_id)
    if not thread or thread.project_id != project_id:
        raise HTTPException(status_code=404, detail="Plot thread not found")
    await db.delete(thread)
