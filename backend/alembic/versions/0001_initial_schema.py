"""
Initial schema — Novel Writing Assistant v4

Creates the pgvector extension and all database tables defined in
Technical Design v4 Section 5 (and referenced supporting tables).

Revision: 0001
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Enable pgvector extension ─────────────────────────────────
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")  # for gen_random_uuid()

    # ─────────────────────────────────────────────────────────────
    # series
    # ─────────────────────────────────────────────────────────────
    op.create_table(
        "series",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("book_order", postgresql.JSONB, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ─────────────────────────────────────────────────────────────
    # projects
    # ─────────────────────────────────────────────────────────────
    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("series_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("series.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("genre", sa.Text, nullable=True),
        sa.Column("premise", sa.Text, nullable=True),
        sa.Column("settings", postgresql.JSONB, server_default="{}"),
        sa.Column("cost_spent_cents", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cost_hard_limit_enabled", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ─────────────────────────────────────────────────────────────
    # characters
    # ─────────────────────────────────────────────────────────────
    op.create_table(
        "characters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("bio", sa.Text, nullable=True),
        sa.Column("data", postgresql.JSONB, server_default="{}"),
        sa.Column("thread_ids", postgresql.JSONB, server_default="[]"),
        sa.Column("last_mentioned_chapter", sa.Integer, nullable=True),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_characters_project_id", "characters", ["project_id"])
    op.create_index("ix_characters_name", "characters", ["name"])

    # ─────────────────────────────────────────────────────────────
    # locations
    # ─────────────────────────────────────────────────────────────
    op.create_table(
        "locations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("data", postgresql.JSONB, server_default="{}"),
        sa.Column("last_mentioned_chapter", sa.Integer, nullable=True),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_locations_project_id", "locations", ["project_id"])

    # ─────────────────────────────────────────────────────────────
    # plot_threads
    # ─────────────────────────────────────────────────────────────
    op.create_table(
        "plot_threads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("last_mentioned_chapter", sa.Integer, nullable=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('active','dormant','resolved')", name="ck_plot_thread_status"),
    )
    op.create_index("ix_plot_threads_project_id", "plot_threads", ["project_id"])

    # ─────────────────────────────────────────────────────────────
    # chapters
    # ─────────────────────────────────────────────────────────────
    op.create_table(
        "chapters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chapter_number", sa.Integer, nullable=False),
        sa.Column("title", sa.Text, nullable=True),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("content", sa.Text, nullable=True),
        sa.Column("word_count", sa.Integer, nullable=True),
        sa.Column("version_history", postgresql.JSONB, nullable=True),
        # pgvector column — dimension 768 matches text-embedding-004
        sa.Column("summary_embedding", sa.Text, nullable=True),  # placeholder; overridden below
        sa.Column("needs_revalidation", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("project_id", "chapter_number", name="uq_chapter_project_num"),
    )
    op.create_index("ix_chapters_project_id", "chapters", ["project_id"])
    # Replace TEXT placeholder with actual vector column
    op.execute("ALTER TABLE chapters DROP COLUMN IF EXISTS summary_embedding")
    op.execute("ALTER TABLE chapters ADD COLUMN summary_embedding vector(768)")

    # ─────────────────────────────────────────────────────────────
    # chapter_state_snapshots
    # ─────────────────────────────────────────────────────────────
    op.create_table(
        "chapter_state_snapshots",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("chapter_number", sa.Integer, primary_key=True),
        sa.Column("current_location_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("locations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("party_status", postgresql.JSONB, server_default="{}"),
        sa.Column("known_secrets", postgresql.JSONB, server_default="{}"),
        sa.Column("false_beliefs", postgresql.JSONB, server_default="{}"),
        sa.Column("false_belief_resolutions", postgresql.JSONB, server_default="{}"),
        sa.Column("world_conditions", postgresql.JSONB, server_default="{}"),
    )

    # ─────────────────────────────────────────────────────────────
    # chapter_dependencies
    # ─────────────────────────────────────────────────────────────
    op.create_table(
        "chapter_dependencies",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("chapter_number", sa.Integer, primary_key=True),
        sa.Column("depends_on_chapter", sa.Integer, primary_key=True),
        sa.Column("dependency_type", sa.String(50), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint(
            "dependency_type IN ('plot_thread','character_intro','location_first_visit','revelation')",
            name="ck_dependency_type",
        ),
    )

    # ─────────────────────────────────────────────────────────────
    # prose_checkpoints
    # ─────────────────────────────────────────────────────────────
    op.create_table(
        "prose_checkpoints",
        sa.Column("job_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("checkpoint_num", sa.Integer, primary_key=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ─────────────────────────────────────────────────────────────
    # character_presence
    # ─────────────────────────────────────────────────────────────
    op.create_table(
        "character_presence",
        sa.Column("character_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("chapter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("chapters.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("chapter_number", sa.Integer, nullable=False),
    )

    # ─────────────────────────────────────────────────────────────
    # outline_chapters
    # ─────────────────────────────────────────────────────────────
    op.create_table(
        "outline_chapters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chapter_number", sa.Integer, nullable=False),
        sa.Column("title", sa.Text, nullable=True),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("beats", postgresql.JSONB, server_default="[]"),
        sa.Column("template_slot", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_outline_chapters_project_id", "outline_chapters", ["project_id"])

    # ─────────────────────────────────────────────────────────────
    # timeline_cells
    # ─────────────────────────────────────────────────────────────
    op.create_table(
        "timeline_cells",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chapter_number", sa.Integer, nullable=False),
        sa.Column("plotline_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("plot_threads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scene_title", sa.Text, nullable=True),
        sa.Column("scene_summary", sa.Text, nullable=True),
        sa.Column("tension_score", sa.Integer, nullable=True),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        sa.Column("data", postgresql.JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ─────────────────────────────────────────────────────────────
    # bible_events
    # ─────────────────────────────────────────────────────────────
    op.create_table(
        "bible_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chapter_number", sa.Integer, nullable=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("changes", postgresql.JSONB, nullable=False),
        sa.Column("entity_snapshot", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_bible_events_project_id", "bible_events", ["project_id"])
    op.create_index("ix_bible_events_created_at", "bible_events", ["created_at"])

    # ─────────────────────────────────────────────────────────────
    # pending_bible_updates
    # ─────────────────────────────────────────────────────────────
    op.create_table(
        "pending_bible_updates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chapter_number", sa.Integer, nullable=True),
        sa.Column("entity_type", sa.String(50), nullable=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("proposed_changes", postgresql.JSONB, nullable=False),
        sa.Column("entity_version_at_proposal", sa.Integer, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("user_edited_value", postgresql.JSONB, nullable=True),
        sa.Column("source", sa.String(50), nullable=True),
        sa.Column("source_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('pending','accepted','rejected','edited')", name="ck_pending_status"),
        sa.CheckConstraint("source IN ('ai_delta','user_prose_edit','user_manual')", name="ck_pending_source"),
    )
    op.create_index("ix_pending_bible_updates_project_id", "pending_bible_updates", ["project_id"])
    op.create_index("ix_pending_bible_updates_created_at", "pending_bible_updates", ["created_at"])

    # ─────────────────────────────────────────────────────────────
    # prompt_templates
    # ─────────────────────────────────────────────────────────────
    op.create_table(
        "prompt_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("stage", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("template_text", sa.Text, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_prompt_templates_name", "prompt_templates", ["name"])

    # ─────────────────────────────────────────────────────────────
    # prompt_template_activations
    # ─────────────────────────────────────────────────────────────
    op.create_table(
        "prompt_template_activations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("template_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prompt_templates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stage", sa.String(20), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reason", sa.Text, nullable=True),
    )

    # ─────────────────────────────────────────────────────────────
    # generation_logs
    # ─────────────────────────────────────────────────────────────
    op.create_table(
        "generation_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("chapter_number", sa.Integer, nullable=True),
        sa.Column("stage", sa.String(20), nullable=True),
        sa.Column("prompt_template_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("model", sa.String(20), nullable=True),
        sa.Column("input_tokens", sa.Integer, nullable=True),
        sa.Column("output_tokens", sa.Integer, nullable=True),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column("user_accepted", sa.Boolean, nullable=True),
        sa.Column("user_rating", sa.Integer, nullable=True),
        sa.Column("experiment_id", sa.Text, nullable=True),
        sa.Column("variant", sa.String(20), nullable=True),
        sa.Column("maturity_level", sa.String(20), nullable=True),
        sa.Column("scene_intensity", sa.String(20), nullable=True),
        sa.Column("safety_blocked", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("blocked_twice", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("ner_guard_triggered", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_generation_logs_project_id", "generation_logs", ["project_id"])
    op.create_index("ix_generation_logs_job_id", "generation_logs", ["job_id"])
    op.create_index("ix_generation_logs_created_at", "generation_logs", ["created_at"])

    # ─────────────────────────────────────────────────────────────
    # dialogue_sessions
    # ─────────────────────────────────────────────────────────────
    op.create_table(
        "dialogue_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chapter_number", sa.Integer, nullable=True),
        sa.Column("participants", postgresql.JSONB, server_default="[]"),
        sa.Column("scene_context", sa.Text, nullable=True),
        sa.Column("exchange_history", postgresql.JSONB, server_default="[]"),
        sa.Column("compressed_summary", sa.Text, nullable=True),
        sa.Column("subtext_beats", postgresql.JSONB, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_dialogue_sessions_project_id", "dialogue_sessions", ["project_id"])

    # ─────────────────────────────────────────────────────────────
    # style_profiles
    # ─────────────────────────────────────────────────────────────
    op.create_table(
        "style_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("preset", sa.String(30), nullable=False, server_default="custom"),
        sa.Column("banned_words", postgresql.JSONB, server_default="[]"),
        sa.Column("sentence_length", sa.String(20), nullable=True),
        sa.Column("adj_density", sa.String(20), nullable=True),
        sa.Column("env_detail", sa.String(20), nullable=True),
        sa.Column("dialogue_ratio", sa.String(20), nullable=True),
        sa.Column("tone_ceiling", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_style_profiles_project_id", "style_profiles", ["project_id"])

    # ─────────────────────────────────────────────────────────────
    # chapter_analytics
    # ─────────────────────────────────────────────────────────────
    op.create_table(
        "chapter_analytics",
        sa.Column("chapter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("chapters.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("word_count", sa.Integer, nullable=True),
        sa.Column("dialogue_ratio", sa.Float, nullable=True),
        sa.Column("avg_sentence_length", sa.Float, nullable=True),
        sa.Column("filter_word_density", sa.Float, nullable=True),
        sa.Column("adverb_density", sa.Float, nullable=True),
        sa.Column("tension_score", sa.Integer, nullable=True),
        sa.Column("consistency_score", sa.Float, nullable=True),
        sa.Column("knowledge_leakage_count", sa.Integer, nullable=True),
        sa.Column("timeline_violation_count", sa.Integer, nullable=True),
        sa.Column("false_belief_violation_count", sa.Integer, nullable=True),
        sa.Column("safety_block_count", sa.Integer, nullable=True),
        sa.Column("ner_guard_trigger_count", sa.Integer, nullable=True),
        sa.Column("flags", postgresql.ARRAY(sa.Text), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ─────────────────────────────────────────────────────────────
    # eval_experiments
    # ─────────────────────────────────────────────────────────────
    op.create_table(
        "eval_experiments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.Text, nullable=False, unique=True),
        sa.Column("stage", sa.String(20), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("variants", postgresql.JSONB, nullable=False),
        sa.Column("traffic_split", sa.Float, nullable=False, server_default="0.5"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('active','paused','completed')", name="ck_exp_status"),
    )

    # ─────────────────────────────────────────────────────────────
    # eval_results
    # ─────────────────────────────────────────────────────────────
    op.create_table(
        "eval_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("experiment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("eval_experiments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("generation_log_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("generation_logs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("stage", sa.String(20), nullable=True),
        sa.Column("variant", sa.String(20), nullable=True),
        sa.Column("rubric_scores", postgresql.JSONB, server_default="{}"),
        sa.Column("overall_score", sa.Float, nullable=True),
        sa.Column("passed", sa.Boolean, nullable=True),
        sa.Column("judge_reasoning", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_eval_results_experiment_id", "eval_results", ["experiment_id"])
    op.create_index("ix_eval_results_created_at", "eval_results", ["created_at"])

    # ─────────────────────────────────────────────────────────────
    # Index: pgvector cosine similarity on chapters.summary_embedding
    # HNSW index for fast ANN search (Section 16)
    # ─────────────────────────────────────────────────────────────
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_chapters_summary_embedding "
        "ON chapters USING hnsw (summary_embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    # Drop in reverse FK order
    op.drop_table("eval_results")
    op.drop_table("eval_experiments")
    op.drop_table("chapter_analytics")
    op.drop_table("style_profiles")
    op.drop_table("dialogue_sessions")
    op.drop_table("generation_logs")
    op.drop_table("prompt_template_activations")
    op.drop_table("prompt_templates")
    op.drop_table("pending_bible_updates")
    op.drop_table("bible_events")
    op.drop_table("timeline_cells")
    op.drop_table("outline_chapters")
    op.drop_table("character_presence")
    op.drop_table("prose_checkpoints")
    op.drop_table("chapter_dependencies")
    op.drop_table("chapter_state_snapshots")
    op.drop_table("chapters")
    op.drop_table("plot_threads")
    op.drop_table("locations")
    op.drop_table("characters")
    op.drop_table("projects")
    op.drop_table("series")
    op.execute("DROP EXTENSION IF EXISTS vector")
