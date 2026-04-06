"""
app/routers/projects.py — Project CRUD endpoints.
Phase 1: Stubs with correct HTTP signatures.
Full CRUD logic implemented in Phase 1 execution (this file).
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.dependencies import DbDep, CurrentUser
from app.models.project import Project, Series
from app.schemas.common import NotImplementedResponse
from app.schemas.project import (
    ProjectCreate,
    ProjectRead,
    ProjectUpdate,
    ProjectCostRead,
    SeriesCreate,
    SeriesRead,
)

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreate,
    db: DbDep,
    user: CurrentUser,
):
    """Create a new project (novel)."""
    project = Project(
        user_id=user.id,
        title=body.title,
        genre=body.genre,
        premise=body.premise,
        series_id=body.series_id,
        settings=body.settings.model_dump(),
    )
    db.add(project)
    await db.flush()
    await db.refresh(project)
    return project


@router.get("", response_model=list[ProjectRead])
async def list_projects(db: DbDep, user: CurrentUser):
    """List all projects for the current user."""
    result = await db.execute(
        select(Project).where(Project.user_id == user.id).order_by(Project.updated_at.desc())
    )
    return result.scalars().all()


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(project_id: uuid.UUID, db: DbDep, user: CurrentUser):
    """Fetch a single project by ID."""
    project = await db.get(Project, project_id)
    if not project or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(
    project_id: uuid.UUID,
    body: ProjectUpdate,
    db: DbDep,
    user: CurrentUser,
):
    """Partially update project metadata."""
    project = await db.get(Project, project_id)
    if not project or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    update_data = body.model_dump(exclude_none=True)
    if "settings" in update_data:
        # Merge settings instead of replacing
        project.settings = {**project.settings, **update_data.pop("settings").model_dump()}
    for k, v in update_data.items():
        setattr(project, k, v)
    await db.flush()
    await db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project_id: uuid.UUID, db: DbDep, user: CurrentUser):
    """Delete a project and all its data (cascade)."""
    project = await db.get(Project, project_id)
    if not project or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    await db.delete(project)


@router.get("/{project_id}/cost", response_model=ProjectCostRead)
async def get_project_cost(project_id: uuid.UUID, db: DbDep, user: CurrentUser):
    """Return cost usage vs budget for a project (Section 36)."""
    project = await db.get(Project, project_id)
    if not project or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    budget = project.settings.get("cost_budget_cents")
    pct = (project.cost_spent_cents / budget) if budget else None
    return ProjectCostRead(
        project_id=project.id,
        spent_cents=project.cost_spent_cents,
        budget_cents=budget,
        pct=pct,
        hard_limit_enabled=project.cost_hard_limit_enabled,
    )


@router.post("/{project_id}/apply-template", response_model=NotImplementedResponse)
async def apply_plot_template(project_id: uuid.UUID, db: DbDep, user: CurrentUser):
    """Apply a plot structure template (Phase 7)."""
    return NotImplementedResponse()


@router.get("/{project_id}/timeline", response_model=NotImplementedResponse)
async def get_timeline(project_id: uuid.UUID, db: DbDep, user: CurrentUser):
    """Return timeline grid data (Phase 5)."""
    return NotImplementedResponse()


@router.post("/{project_id}/timeline/cells", response_model=NotImplementedResponse)
async def upsert_timeline_cell(project_id: uuid.UUID, db: DbDep, user: CurrentUser):
    """Create or update a timeline cell (Phase 5)."""
    return NotImplementedResponse()


@router.get("/{project_id}/story-map", response_model=NotImplementedResponse)
async def get_story_map(project_id: uuid.UUID, db: DbDep, user: CurrentUser):
    """Return tension + plotline activity data for recharts (Phase 5)."""
    return NotImplementedResponse()


@router.post("/{project_id}/reorder-chapters", response_model=NotImplementedResponse)
async def reorder_chapters(project_id: uuid.UUID, db: DbDep, user: CurrentUser):
    """Reorder chapters with lazy revalidation (Phase 5, Section 31)."""
    return NotImplementedResponse()


# ── Series ────────────────────────────────────────────────────────
series_router = APIRouter(prefix="/series", tags=["series"])


@series_router.get("", response_model=list[SeriesRead])
async def list_series(db: DbDep, user: CurrentUser):
    result = await db.execute(
        select(Series).where(Series.user_id == user.id).order_by(Series.title)
    )
    return result.scalars().all()


@series_router.post("", response_model=SeriesRead, status_code=status.HTTP_201_CREATED)
async def create_series(body: SeriesCreate, db: DbDep, user: CurrentUser):
    s = Series(user_id=user.id, title=body.title, description=body.description)
    db.add(s)
    await db.flush()
    await db.refresh(s)
    return s
