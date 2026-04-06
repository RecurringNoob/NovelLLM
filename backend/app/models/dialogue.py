"""
app/models/dialogue.py — SQLAlchemy ORM model for stateful dialogue sessions.
See Section 9 of the Technical Design v4.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DialogueSession(Base):
    """
    A stateful multi-turn dialogue simulation session.

    exchange_history JSONB schema (list of turns):
    [
      {
        "turn": 1,
        "speaker": "Lyra",
        "dialogue": "I know what you did, Kael.",
        "internal_thought": "...",    # optional
        "blocking_note": "...",       # optional stage direction
        "subtext_beats": "..."        # optional
      },
      ...
    ]

    When len(exchange_history) > COMPRESSION_THRESHOLD (20 turns),
    older turns are compressed into compressed_summary (Section 9).

    Export-to-Prose action creates a Stage 3 job that converts this
    session into standard novel prose (Section 19).
    """

    __tablename__ = "dialogue_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chapter_number: Mapped[int | None] = mapped_column(Integer)

    # Participating character names
    participants: Mapped[list] = mapped_column(JSONB, default=list)

    # Scene context for the dialogue
    scene_context: Mapped[str | None] = mapped_column(Text)

    # Full turn history (may be truncated to last 10 when compressed)
    exchange_history: Mapped[list] = mapped_column(JSONB, default=list)

    # Gemini Flash summary of compressed turns (Section 9)
    compressed_summary: Mapped[str | None] = mapped_column(Text)

    # Subtext beats injected from Stage 2 (JSONB list of beat strings)
    subtext_beats: Mapped[list] = mapped_column(JSONB, default=list)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
