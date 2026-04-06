"""
app/models/project.py — SQLAlchemy ORM models for projects and series.
Maps directly to Section 5 of the Technical Design v4.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
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


class Series(Base):
    """
    A series groups multiple Project (books).
    One Series → many Projects.
    """

    __tablename__ = "series"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # Book order: [project_id, ...] in reading sequence
    book_order: Mapped[dict] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    projects: Mapped[list["Project"]] = relationship(
        "Project", back_populates="series", lazy="selectin"
    )


class Project(Base):
    """
    Top-level entity representing one novel/book.

    settings JSONB schema (from TDD Section 5):
    {
      "tone": str,
      "pov": str,
      "auto_consistency": bool,
      "writing_mode": "assist" | "co-write" | "auto",
      "maturity_level": "general" | "mature" | "explicit",
      "tone_ceiling": str | null,
      "cost_budget_cents": int
    }
    """

    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    series_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("series.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    genre: Mapped[str | None] = mapped_column(Text)
    premise: Mapped[str | None] = mapped_column(Text)

    # JSONB settings blob — see docstring above for schema
    settings: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Cost tracking (Section 36)
    cost_spent_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_hard_limit_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # ── Relationships ─────────────────────────────────────────────
    series: Mapped["Series | None"] = relationship(
        "Series", back_populates="projects"
    )
    chapters: Mapped[list["Chapter"]] = relationship(  # noqa: F821
        "Chapter", back_populates="project", cascade="all, delete-orphan"
    )
    characters: Mapped[list["Character"]] = relationship(  # noqa: F821
        "Character", back_populates="project", cascade="all, delete-orphan"
    )
    locations: Mapped[list["Location"]] = relationship(  # noqa: F821
        "Location", back_populates="project", cascade="all, delete-orphan"
    )
    plot_threads: Mapped[list["PlotThread"]] = relationship(  # noqa: F821
        "PlotThread", back_populates="project", cascade="all, delete-orphan"
    )
    style_profiles: Mapped[list["StyleProfile"]] = relationship(  # noqa: F821
        "StyleProfile", back_populates="project", cascade="all, delete-orphan"
    )
    pending_bible_updates: Mapped[list["PendingBibleUpdate"]] = relationship(  # noqa: F821
        "PendingBibleUpdate", back_populates="project", cascade="all, delete-orphan"
    )
