"""
app/models/eval.py — A/B testing and LLM-as-Judge eval tables.
See Sections 28–29 of the Technical Design v4.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class EvalExperiment(Base):
    """
    An A/B experiment configuration (Section 28).

    variants JSONB schema:
    {
      "control": <prompt_template_id>,
      "treatment": <prompt_template_id>
    }

    traffic_split: fraction of traffic to route to "treatment" (0.0–1.0).
    Bucket assignment: md5(project_id + experiment_id) % 100 < split * 100 → treatment.
    """

    __tablename__ = "eval_experiments"
    __table_args__ = (
        CheckConstraint("status IN ('active','paused','completed')", name="ck_exp_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    stage: Mapped[str] = mapped_column(String(20), nullable=False)  # "0"–"6"
    description: Mapped[str | None] = mapped_column(Text)

    variants: Mapped[dict] = mapped_column(JSONB, nullable=False)
    traffic_split: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)

    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # ── Relationships ─────────────────────────────────────────────
    results: Mapped[list["EvalResult"]] = relationship(
        "EvalResult", back_populates="experiment"
    )


class EvalResult(Base):
    """
    LLM-as-Judge evaluation result for a single generation (Section 29).

    rubric_scores JSONB schema (per-stage criteria):
    {
      "json_validity": 1.0,
      "pov_consistency": 0.9,
      "knowledge_leakage": 1.0,
      "false_belief_violation": 1.0,
      "ner_guard_respected": 1.0,
      "length_guard_respected": 1.0,
      "schema_validity": 1.0
    }

    overall_score: weighted average of rubric_scores (0.0–1.0).
    Fail threshold: 0.75 (Section 29 CI gate).
    """

    __tablename__ = "eval_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    experiment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("eval_experiments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    generation_log_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("generation_logs.id", ondelete="SET NULL"),
        nullable=True,
    )

    stage: Mapped[str | None] = mapped_column(String(20))
    variant: Mapped[str | None] = mapped_column(String(20))

    # Per-criterion scores from the LLM judge (Section 29)
    rubric_scores: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Weighted aggregate
    overall_score: Mapped[float | None] = mapped_column(Float)

    # Did this result pass the CI gate threshold (≥ 0.75)?
    passed: Mapped[bool | None] = mapped_column(Boolean)

    # Judge model output for debugging
    judge_reasoning: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    # ── Relationships ─────────────────────────────────────────────
    experiment: Mapped["EvalExperiment | None"] = relationship(
        "EvalExperiment", back_populates="results"
    )
