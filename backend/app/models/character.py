"""
app/models/character.py — SQLAlchemy ORM models for characters.

Tables:
  - characters
  - character_presence  (pivot: character × chapter)
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Character(Base):
    """
    A character within a project.

    data JSONB typical schema:
    {
      "bio": str,
      "arc_stage": "setup"|"buildup"|"confrontation"|"crisis"|"resolution",
      "goals": [str],
      "secrets": [str],
      "appearance": str,
      "voice_notes": str,
      "summary": str      # ← used by Lore-Check snippets (Section 12)
    }

    thread_ids: list of PlotThread UUIDs this character is linked to.
    version: incremented on every AI or user edit (OCC, Section 18).
    """

    __tablename__ = "characters"

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

    # Flattened bio for quick access
    bio: Mapped[str | None] = mapped_column(Text)

    # Full structured data blob
    data: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Linked plot thread UUIDs (array for scoring in Section 11)
    thread_ids: Mapped[list] = mapped_column(JSONB, default=list)

    # Decay tracking: which chapter this character last appeared in
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
        "Project", back_populates="characters"
    )
    presences: Mapped[list["CharacterPresence"]] = relationship(
        "CharacterPresence",
        back_populates="character",
        cascade="all, delete-orphan",
    )


class CharacterPresence(Base):
    """
    Records which chapters a character is present in.
    Used by the Information Asymmetry Engine (Section 8) to determine
    which events a character could plausibly know about.
    """

    __tablename__ = "character_presence"

    character_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("characters.id", ondelete="CASCADE"),
        primary_key=True,
    )
    chapter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chapters.id", ondelete="CASCADE"),
        primary_key=True,
    )
    chapter_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # ── Relationships ─────────────────────────────────────────────
    character: Mapped["Character"] = relationship(
        "Character", back_populates="presences"
    )
    chapter: Mapped["Chapter"] = relationship(  # noqa: F821
        "Chapter", back_populates="character_presences",
        foreign_keys=[chapter_id],
    )
