"""
app/models/world.py — SQLAlchemy ORM models for worldbuilding entities.

Tables:
  - locations
  - plot_threads
  - outline_chapters
  - timeline_cells
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Location(Base):
    """
    A named place within the project world.

    data JSONB typical schema:
    {
      "description": str,
      "geography": str,
      "notable_features": [str],
      "summary": str      # ← used by Lore-Check snippets
    }
    """

    __tablename__ = "locations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    data: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Decay tracking (Section 11)
    last_mentioned_chapter: Mapped[int | None] = mapped_column(Integer)

    # OCC version counter (Section 18)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # ── Relationships ─────────────────────────────────────────────
    project: Mapped["Project"] = relationship(  # noqa: F821
        "Project", back_populates="locations"
    )


class PlotThread(Base):
    """
    A named narrative thread (subplot, mystery, arc, etc.).

    status lifecycle: active → dormant → resolved
    Warning triggered in Stage 6 if active and not mentioned in 3+ chapters (Section 20).
    """

    __tablename__ = "plot_threads"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active','dormant','resolved')",
            name="ck_plot_thread_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)

    # Decay tracking — which chapter this thread was last explicitly mentioned
    last_mentioned_chapter: Mapped[int | None] = mapped_column(Integer)

    # Optional link to an entity (character, location, artifact) that anchors the thread
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # OCC version counter
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # ── Relationships ─────────────────────────────────────────────
    project: Mapped["Project"] = relationship(  # noqa: F821
        "Project", back_populates="plot_threads"
    )


class OutlineChapter(Base):
    """
    The structured outline scaffold for a chapter.
    Separate from the Chapter table — outline exists before prose is generated.
    """

    __tablename__ = "outline_chapters"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chapter_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)

    # AI-generated beats list (Stage 2 output, stored as JSON array)
    beats: Mapped[list] = mapped_column(JSONB, default=list)

    # Plot template slot (e.g. "save_the_cat:fun_and_games", "hero_journey:ordeal")
    template_slot: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TimelineCell(Base):
    """
    A cell in the visual timeline grid (chapter × plotline).
    Drag-drop positions are stored in this table.
    Used by TimelinePage (Section 20, dnd-kit).
    """

    __tablename__ = "timeline_cells"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chapter_number: Mapped[int] = mapped_column(Integer, nullable=False)
    plotline_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plot_threads.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Scene card data
    scene_title: Mapped[str | None] = mapped_column(Text)
    scene_summary: Mapped[str | None] = mapped_column(Text)
    tension_score: Mapped[int | None] = mapped_column(Integer)  # 1–10

    # Position within a cell (multiple scenes can share a cell)
    position: Mapped[int] = mapped_column(Integer, default=0)

    data: Mapped[dict] = mapped_column(JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
