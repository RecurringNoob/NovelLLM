"""
app/models/job.py — GenerationJob ORM model.

Tracks async pipeline job state.
Written to DB when a /generate request comes in;
updated by the worker as it moves through stages.
Referenced by safety-block recovery (Section 2.5) and
"Continue from here" (Section 37).
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
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class GenerationJob(Base):
    """
    Tracks the lifecycle of an AI generation pipeline run.

    Status transitions:
      queued → running → done
                      → failed
                      → safety_blocked

    beats: stored after Stage 2 so user can edit before Stage 3 starts
           (co-write / assist modes).

    partial_prose + blocked_at_checkpoint: set by CheckpointedProseStream
    on a safety block (Section 2.5); used by 'Continue from here' (Section 37).
    """

    __tablename__ = "generation_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','running','done','failed','safety_blocked')",
            name="ck_job_status",
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
    status: Mapped[str] = mapped_column(String(30), default="queued", nullable=False)
    stage: Mapped[str | None] = mapped_column(String(10))
    mode: Mapped[str | None] = mapped_column(String(30))
    maturity_level: Mapped[str | None] = mapped_column(String(20))
    scene_intensity: Mapped[str | None] = mapped_column(String(20))

    # Stage 0 output (intent JSON)
    intent: Mapped[dict | None] = mapped_column(JSONB)

    # Stage 2 output (beats list) — stored for user edit gate
    beats: Mapped[list | None] = mapped_column(JSONB)

    # Safety-block recovery fields (Section 2.5)
    partial_prose: Mapped[str | None] = mapped_column(Text)
    blocked_at_checkpoint: Mapped[int | None] = mapped_column(Integer)
    blocked_twice: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    error_message: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
