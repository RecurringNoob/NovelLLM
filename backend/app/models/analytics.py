"""
app/models/analytics.py — Chapter analytics & consistency metrics.
See Section 5.2 of the Technical Design v4.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ARRAY, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ChapterAnalytics(Base):
    """
    Measurable consistency metrics for each chapter (Section 1 — NFRs).

    Updated by Stage 6 after each consistency check run.
    All metrics are reset on lazy revalidation completion.

    Key metrics (from Section 1):
      - consistency_score          → fraction 0.0–1.0 (target ≥ 0.95)
      - knowledge_leakage_count    → POV violations
      - timeline_violation_count   → causal contradictions (target < 1)
      - false_belief_violation_count → belief inconsistencies (target < 0.1)
      - safety_block_count         → Stage 3 SAFETY events for this chapter
      - ner_guard_trigger_count    → Stage 4 NER guard rejections
    """

    __tablename__ = "chapter_analytics"

    chapter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chapters.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Prose statistics
    word_count: Mapped[int | None] = mapped_column(Integer)
    dialogue_ratio: Mapped[float | None] = mapped_column(Float)
    avg_sentence_length: Mapped[float | None] = mapped_column(Float)
    filter_word_density: Mapped[float | None] = mapped_column(Float)
    adverb_density: Mapped[float | None] = mapped_column(Float)
    tension_score: Mapped[int | None] = mapped_column(Integer)  # 1–10

    # Consistency metrics (Section 1, Measurable)
    consistency_score: Mapped[float | None] = mapped_column(Float)
    knowledge_leakage_count: Mapped[int | None] = mapped_column(Integer)
    timeline_violation_count: Mapped[int | None] = mapped_column(Integer)
    false_belief_violation_count: Mapped[int | None] = mapped_column(Integer)

    # Safety & NER guard metrics (Section 27)
    safety_block_count: Mapped[int | None] = mapped_column(Integer)
    ner_guard_trigger_count: Mapped[int | None] = mapped_column(Integer)

    # Free-form flag list (e.g. ["pov_violation", "timeline_gap"])
    flags: Mapped[list | None] = mapped_column(ARRAY(Text))

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # ── Relationships ─────────────────────────────────────────────
    chapter: Mapped["Chapter"] = relationship(  # noqa: F821
        "Chapter", back_populates="analytics"
    )
