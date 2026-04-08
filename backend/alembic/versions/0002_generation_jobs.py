"""
Phase 2 additions:
  - generation_jobs table (tracks pipeline job state; used by Phase 2+ worker)
  - partial_prose / blocked_at_checkpoint columns on generation_jobs
    (referenced in Section 2.5 safety block recovery)
  - No schema changes to existing tables — all models were correct in 0001.

Revision: 0002
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ─────────────────────────────────────────────────────────────
    # generation_jobs — tracks async pipeline job state
    # ─────────────────────────────────────────────────────────────
    op.create_table(
        "generation_jobs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("chapter_number", sa.Integer, nullable=True),
        # "queued" | "running" | "done" | "failed" | "safety_blocked"
        sa.Column("status", sa.String(30), nullable=False, server_default="queued"),
        sa.Column("stage", sa.String(10), nullable=True),  # current stage being executed
        sa.Column("mode", sa.String(30), nullable=True),   # "co-write"|"auto"|"continue_from_manual_write"
        sa.Column("maturity_level", sa.String(20), nullable=True),
        sa.Column("scene_intensity", sa.String(20), nullable=True),
        # Intent JSON from Stage 0
        sa.Column("intent", postgresql.JSONB, nullable=True),
        # Beats from Stage 2 (stored so user can edit before Stage 3)
        sa.Column("beats", postgresql.JSONB, nullable=True),
        # Partial prose saved at last checkpoint before a safety block
        sa.Column("partial_prose", sa.Text, nullable=True),
        sa.Column("blocked_at_checkpoint", sa.Integer, nullable=True),
        sa.Column("blocked_twice", sa.Boolean, nullable=False, server_default="false"),
        # Error details if status=failed
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('queued','running','done','failed','safety_blocked')",
            name="ck_job_status",
        ),
    )
    op.create_index("ix_generation_jobs_project_id", "generation_jobs", ["project_id"])
    op.create_index("ix_generation_jobs_status", "generation_jobs", ["status"])


def downgrade() -> None:
    op.drop_table("generation_jobs")
