"""
app/models/style.py — SQLAlchemy ORM model for style profiles.
See Section 13 of the Technical Design v4.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class StyleProfile(Base):
    """
    A named style profile for Stage 4 prose refinement.

    Built-in presets (Section 13):
      - hemingway    → terse, low adj, sparse env, medium dialogue
      - tolkien      → expansive, high adj, rich env, low dialogue
      - le_carre     → balanced, medium adj, moderate env, high dialogue
      - mccarthy     → terse, low adj, moderate env, low dialogue
      - custom       → user-defined

    banned_words: injected into Stage 4 "BANNED WORDS" instruction.
    tone_ceiling: forwarded to Stage 4 TONE CEILING instruction (Section 2.6).
    is_active: only one profile per project is active at a time.
    """

    __tablename__ = "style_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)

    # One of the built-in preset names or "custom"
    preset: Mapped[str] = mapped_column(String(30), default="custom", nullable=False)

    # Words explicitly banned from Stage 4 output
    banned_words: Mapped[list] = mapped_column(JSONB, default=list)

    # Style configuration
    sentence_length: Mapped[str | None] = mapped_column(
        String(20)
    )  # "terse" | "balanced" | "expansive"
    adj_density: Mapped[str | None] = mapped_column(String(20))   # "low" | "medium" | "high"
    env_detail: Mapped[str | None] = mapped_column(String(20))    # "sparse" | "moderate" | "rich"
    dialogue_ratio: Mapped[str | None] = mapped_column(String(20))  # "low" | "medium" | "high"

    # Tone ceiling for mature content gating (Section 2.6)
    tone_ceiling: Mapped[str | None] = mapped_column(Text)

    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # ── Relationships ─────────────────────────────────────────────
    project: Mapped["Project"] = relationship(  # noqa: F821
        "Project", back_populates="style_profiles"
    )
