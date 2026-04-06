"""
app/models/chapter.py — SQLAlchemy ORM models for chapters and their state.

Tables:
  - chapters
  - chapter_state_snapshots
  - chapter_dependencies
  - prose_checkpoints
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
    UniqueConstraint,
    Boolean,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

try:
    from pgvector.sqlalchemy import Vector
    PGVECTOR_AVAILABLE = True
except ImportError:
    # Fallback for environments without pgvector installed at import time
    from sqlalchemy import JSON as Vector  # type: ignore[assignment]
    PGVECTOR_AVAILABLE = False


class Chapter(Base):
    """
    One chapter within a project.
    v4 additions: needs_revalidation flag (Section 31).
    """

    __tablename__ = "chapters"
    __table_args__ = (
        UniqueConstraint("project_id", "chapter_number", name="uq_chapter_project_num"),
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
    chapter_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str | None] = mapped_column(Text)
    word_count: Mapped[int | None] = mapped_column(Integer)

    # Event-sourced version history snapshot (lightweight list of diffs)
    version_history: Mapped[dict | None] = mapped_column(JSONB)

    # pgvector embedding for semantic search (Section 16)
    # Dimension 768 matches text-embedding-004 output
    summary_embedding: Mapped[list | None] = mapped_column(
        Vector(768) if PGVECTOR_AVAILABLE else JSONB,
        nullable=True,
    )

    # Lazy revalidation flag (Section 31, v4)
    needs_revalidation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # ── Relationships ─────────────────────────────────────────────
    project: Mapped["Project"] = relationship(  # noqa: F821
        "Project", back_populates="chapters"
    )
    state_snapshot: Mapped["ChapterStateSnapshot | None"] = relationship(
        "ChapterStateSnapshot",
        primaryjoin="and_(Chapter.project_id==ChapterStateSnapshot.project_id, "
                    "Chapter.chapter_number==ChapterStateSnapshot.chapter_number)",
        foreign_keys="[ChapterStateSnapshot.project_id, ChapterStateSnapshot.chapter_number]",
        viewonly=True,
    )
    analytics: Mapped["ChapterAnalytics | None"] = relationship(  # noqa: F821
        "ChapterAnalytics", back_populates="chapter", uselist=False
    )
    character_presences: Mapped[list["CharacterPresence"]] = relationship(  # noqa: F821
        "CharacterPresence", back_populates="chapter",
        primaryjoin="Chapter.id==CharacterPresence.chapter_id",
    )


class ChapterStateSnapshot(Base):
    """
    Point-in-time snapshot of narrative state as of end of each chapter.
    Used by Stage 1 context assembler and Information Asymmetry Engine.

    false_belief_resolutions schema (v4):
    {
      "CharacterName": {
        "The false belief text": {
          "resolved_in_chapter": <int>,
          "evidence": "<verbatim quote from prose>"
        }
      }
    }
    """

    __tablename__ = "chapter_state_snapshots"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True,
    )
    chapter_number: Mapped[int] = mapped_column(Integer, primary_key=True)

    current_location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="SET NULL"),
        nullable=True,
    )

    # {"character": "status"} — e.g. {"Lyra": "captured", "Kael": "at large"}
    party_status: Mapped[dict] = mapped_column(JSONB, default=dict)

    # {"character": ["secret1", "secret2"]}
    known_secrets: Mapped[dict] = mapped_column(JSONB, default=dict)

    # {"character": ["false belief string", ...]}
    false_beliefs: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Explicit resolution records — requires evidence quote (Section 32, v4)
    false_belief_resolutions: Mapped[dict] = mapped_column(JSONB, default=dict)

    # {"condition": "state"} — e.g. {"war": "active", "binding_spell": "intact"}
    world_conditions: Mapped[dict] = mapped_column(JSONB, default=dict)


class ChapterDependency(Base):
    """
    Tracks which chapters depend on earlier chapters for cascade revalidation.
    (Section 31 — lazy revalidation uses this to determine first_affected.)
    """

    __tablename__ = "chapter_dependencies"
    __table_args__ = (
        CheckConstraint(
            "dependency_type IN ('plot_thread','character_intro','location_first_visit','revelation')",
            name="ck_dependency_type",
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True,
    )
    chapter_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    depends_on_chapter: Mapped[int] = mapped_column(Integer, primary_key=True)

    dependency_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class ProseCheckpoint(Base):
    """
    Checkpointed prose fragments saved every 500 words during Stage 3 streaming.
    Used for safety-block recovery and "Continue from here" (Section 2.5, Section 37).
    These are recovery artifacts — NOT reuse cache (stored in DB, not Redis).
    """

    __tablename__ = "prose_checkpoints"

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True
    )
    checkpoint_num: Mapped[int] = mapped_column(Integer, primary_key=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
