"""
app/models/bible.py — SQLAlchemy ORM models for the Story Bible system.

Tables:
  - bible_events            (event-sourced mutations)
  - pending_bible_updates   (AI-proposed changes awaiting human review)
  - generation_logs         (per-stage telemetry)
  - prompt_templates        (versioned prompt store)
  - prompt_template_activations (rollback audit log)
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
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


class BibleEvent(Base):
    """
    Immutable event log for all story bible mutations (event sourcing).
    Rollback is achieved by replaying events up to a target sequence number.
    """

    __tablename__ = "bible_events"

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

    # Source of the change
    source: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # "ai_delta_accepted" | "ai_delta_edited" | "user_manual"

    entity_type: Mapped[str | None] = mapped_column(String(50))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    # The delta applied (JSONB patch)
    changes: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Snapshot of entity state after this event (for efficient time-travel)
    entity_snapshot: Mapped[dict | None] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class PendingBibleUpdate(Base):
    """
    An AI-proposed bible change awaiting human review.
    Humans can: accept, reject, or edit-then-accept.

    source values (v4):
    - 'ai_delta'        — from Stage 5 delta extractor
    - 'user_prose_edit' — from diff-based prose-to-bible sync (Section 30)
    - 'user_manual'     — from user directly editing the bible

    entity_version_at_proposal: the OCC version when the AI generated this change.
    If the entity has since been updated, a VersionConflictError is raised on accept.
    """

    __tablename__ = "pending_bible_updates"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','accepted','rejected','edited')",
            name="ck_pending_status",
        ),
        CheckConstraint(
            "source IN ('ai_delta','user_prose_edit','user_manual')",
            name="ck_pending_source",
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
    chapter_number: Mapped[int | None] = mapped_column(Integer)

    entity_type: Mapped[str | None] = mapped_column(String(50))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    proposed_changes: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # OCC version of entity when AI proposed this change
    entity_version_at_proposal: Mapped[int | None] = mapped_column(Integer)

    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)

    # If the user edited the proposed_changes before accepting
    user_edited_value: Mapped[dict | None] = mapped_column(JSONB)

    # v4: traceability
    source: Mapped[str | None] = mapped_column(String(50))
    source_job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # ── Relationships ─────────────────────────────────────────────
    project: Mapped["Project"] = relationship(  # noqa: F821
        "Project", back_populates="pending_bible_updates"
    )


class GenerationLog(Base):
    """
    Per-stage generation telemetry.
    v4 additions: maturity_level, scene_intensity, safety_blocked,
    blocked_twice, ner_guard_triggered (Section 5.1, Section 27).
    Used by A/B testing queries (Section 28) and observability (Section 27).
    """

    __tablename__ = "generation_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    chapter_number: Mapped[int | None] = mapped_column(Integer)
    stage: Mapped[str | None] = mapped_column(String(20))  # "0","1","2","3","4","5","6"
    prompt_template_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    model: Mapped[str | None] = mapped_column(String(20))  # "flash" | "pro"
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    user_accepted: Mapped[bool | None] = mapped_column(Boolean)
    user_rating: Mapped[int | None] = mapped_column(Integer)  # 1–5

    # A/B testing fields (Section 28)
    experiment_id: Mapped[str | None] = mapped_column(Text)
    variant: Mapped[str | None] = mapped_column(String(20))  # "control" | "treatment"

    # v4 mature content / safety fields
    maturity_level: Mapped[str | None] = mapped_column(String(20))
    scene_intensity: Mapped[str | None] = mapped_column(String(20))
    safety_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    blocked_twice: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ner_guard_triggered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class PromptTemplate(Base):
    """
    Versioned prompt templates for each pipeline stage.
    Supports rollback via prompt_template_activations (Section 35).
    Only one template per (name, stage) pair should have is_active=True at a time.
    """

    __tablename__ = "prompt_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    stage: Mapped[str] = mapped_column(String(20), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    template_text: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # ── Relationships ─────────────────────────────────────────────
    activations: Mapped[list["PromptTemplateActivation"]] = relationship(
        "PromptTemplateActivation", back_populates="template"
    )


class PromptTemplateActivation(Base):
    """
    Audit log for prompt template activations / rollbacks (Section 35).
    deactivated_at is NULL while the template is currently active.
    """

    __tablename__ = "prompt_template_activations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("prompt_templates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stage: Mapped[str] = mapped_column(String(20), nullable=False)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reason: Mapped[str | None] = mapped_column(Text)

    # ── Relationships ─────────────────────────────────────────────
    template: Mapped["PromptTemplate"] = relationship(
        "PromptTemplate", back_populates="activations"
    )
