"""
tests/test_infrastructure.py — Infrastructure-level tests for the Novel Writing Assistant.

Test categories:
  1. Health Check    — GET /health verifies DB + Redis connectivity
  2. Database Integrity — schema reflection; all expected tables present; pgvector enabled
  3. Config Test     — Settings loads all expected env vars without error

Run with:
    pytest backend/tests/test_infrastructure.py -v

Environment:
    TEST_DATABASE_URL must point to the real (or test) PostgreSQL database.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import inspect, text

pytestmark = pytest.mark.asyncio


# ─────────────────────────────────────────────────────────────────────────────
# Health Check
# ─────────────────────────────────────────────────────────────────────────────

class TestHealthCheck:
    """GET /health should report both DB and Redis as reachable."""

    async def test_health_returns_200(self, async_client):
        response = await async_client.get("/health")
        assert response.status_code == 200, response.text

    async def test_health_db_connected(self, async_client):
        data = response = await async_client.get("/health")
        data = response.json()
        assert data["db"] == "connected", f"DB not connected: {data}"

    async def test_health_redis_connected(self, async_client, fake_redis):
        """
        The client fixture injects FakeRedis. The health endpoint calls redis_ping()
        which uses the module-level pool — which our fixture has replaced with FakeRedis.
        FakeRedis.ping() returns True so the response should be 'connected'.
        """
        response = await async_client.get("/health")
        data = response.json()
        assert data["redis"] == "connected", f"Redis not connected: {data}"

    async def test_health_has_version(self, async_client):
        response = await async_client.get("/health")
        data = response.json()
        assert "version" in data
        assert data["status"] == "ok"

    async def test_health_environment_present(self, async_client):
        response = await async_client.get("/health")
        data = response.json()
        assert "environment" in data


# ─────────────────────────────────────────────────────────────────────────────
# Database Integrity
# ─────────────────────────────────────────────────────────────────────────────

# All 21 tables that must be present in the migrated schema
EXPECTED_TABLES = {
    # Projects & series
    "projects",
    "series",
    # Chapters
    "chapters",
    "chapter_state_snapshots",
    "chapter_dependencies",
    "prose_checkpoints",
    # Characters
    "characters",
    "character_presence",
    # World
    "locations",
    "plot_threads",
    "outline_chapters",
    "timeline_cells",
    # Bible
    "bible_events",
    "pending_bible_updates",
    "generation_logs",
    "prompt_templates",
    "prompt_template_activations",
    # Jobs
    "generation_jobs",
    # Supporting
    "dialogue_sessions",
    "style_profiles",
    "chapter_analytics",
    # A/B
    "eval_experiments",
    "eval_results",
}


class TestDatabaseIntegrity:
    """Verify the schema against the ORM models."""

    @pytest_asyncio.fixture(autouse=True)
    async def _reflect(self, async_engine):
        """Reflect the live schema once per test class run."""
        self._engine = async_engine

    async def test_all_expected_tables_exist(self):
        """
        Reflect live DB schema and assert every expected table is present.
        A missing table indicates a missing or failed migration.
        """
        async with self._engine.connect() as conn:
            tables = await conn.run_sync(
                lambda sync_conn: set(inspect(sync_conn).get_table_names())
            )

        missing = EXPECTED_TABLES - tables
        assert not missing, (
            f"Missing tables in DB schema ({len(missing)} missing):\n"
            + "\n".join(f"  - {t}" for t in sorted(missing))
        )

    async def test_table_count_at_least_20(self):
        """Guard rail: total table count must be ≥ 20 (from TDD spec)."""
        async with self._engine.connect() as conn:
            tables = await conn.run_sync(
                lambda sync_conn: set(inspect(sync_conn).get_table_names())
            )
        assert len(tables) >= 20, f"Only {len(tables)} tables found, expected ≥ 20"

    async def test_pgvector_extension_enabled(self):
        """
        The vector extension is required for chapter semantic search.
        Verify it is installed in the test database.
        """
        async with self._engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT extname FROM pg_extension WHERE extname = 'vector'"
                )
            )
            row = result.fetchone()
        assert row is not None, (
            "pgvector extension is not installed. "
            "Run: CREATE EXTENSION IF NOT EXISTS vector; "
            "or apply migration 0001_initial_schema.py"
        )

    async def test_projects_table_has_occ_columns(self):
        """Spot-check key columns on the projects table."""
        async with self._engine.connect() as conn:
            cols = await conn.run_sync(
                lambda sync_conn: {
                    c["name"]
                    for c in inspect(sync_conn).get_columns("projects")
                }
            )
        required = {"id", "user_id", "title", "settings", "cost_spent_cents", "cost_hard_limit_enabled"}
        missing = required - cols
        assert not missing, f"projects table missing columns: {missing}"

    async def test_pending_bible_updates_has_occ_version(self):
        """Confirm OCC version column exists on pending_bible_updates."""
        async with self._engine.connect() as conn:
            cols = await conn.run_sync(
                lambda sync_conn: {
                    c["name"]
                    for c in inspect(sync_conn).get_columns("pending_bible_updates")
                }
            )
        assert "entity_version_at_proposal" in cols, (
            "pending_bible_updates.entity_version_at_proposal is missing — OCC will not work correctly"
        )

    async def test_generation_jobs_has_safety_columns(self):
        """Confirm Phase 2 safety-block recovery columns exist on generation_jobs."""
        async with self._engine.connect() as conn:
            cols = await conn.run_sync(
                lambda sync_conn: {
                    c["name"]
                    for c in inspect(sync_conn).get_columns("generation_jobs")
                }
            )
        required = {"partial_prose", "blocked_at_checkpoint", "blocked_twice"}
        missing = required - cols
        assert not missing, f"generation_jobs missing safety columns: {missing}"

    async def test_chapters_has_embedding_column(self):
        """chapters.summary_embedding must exist for pgvector ANN search (Phase 8)."""
        async with self._engine.connect() as conn:
            cols = await conn.run_sync(
                lambda sync_conn: {
                    c["name"]
                    for c in inspect(sync_conn).get_columns("chapters")
                }
            )
        assert "summary_embedding" in cols, (
            "chapters.summary_embedding is missing — pgvector semantic search (Phase 8) will fail"
        )

    async def test_chapter_state_snapshots_false_belief_columns(self):
        """Verify false belief columns for Phase 2 evidence guard."""
        async with self._engine.connect() as conn:
            cols = await conn.run_sync(
                lambda sync_conn: {
                    c["name"]
                    for c in inspect(sync_conn).get_columns("chapter_state_snapshots")
                }
            )
        required = {"false_beliefs", "false_belief_resolutions", "party_status", "known_secrets", "world_conditions"}
        missing = required - cols
        assert not missing, f"chapter_state_snapshots missing columns: {missing}"


# ─────────────────────────────────────────────────────────────────────────────
# Config Test
# ─────────────────────────────────────────────────────────────────────────────

class TestConfig:
    """Validate that Settings loads correctly from environment variables."""

    def test_settings_loads_without_error(self):
        """Simply instantiating Settings must not raise."""
        from app.config import Settings
        s = Settings()
        assert s is not None

    def test_settings_has_required_fields(self):
        from app.config import settings
        assert isinstance(settings.database_url, str)
        assert settings.database_url.startswith("postgresql")
        assert isinstance(settings.redis_url, str)
        assert settings.redis_url.startswith("redis")
        assert isinstance(settings.environment, str)

    def test_settings_cors_origins_list_is_list(self):
        from app.config import settings
        origins = settings.cors_origins_list
        assert isinstance(origins, list)
        assert len(origins) >= 1

    def test_settings_dev_user_id_is_valid_uuid(self):
        import uuid as _uuid
        from app.config import settings
        # Should not raise
        parsed = _uuid.UUID(settings.dev_user_id)
        assert parsed is not None

    def test_settings_default_cost_budget_cents_positive(self):
        from app.config import settings
        assert settings.default_cost_budget_cents > 0

    def test_settings_is_development_property(self):
        from app.config import Settings
        s = Settings(environment="development")
        assert s.is_development is True
        s2 = Settings(environment="production")
        assert s2.is_development is False
