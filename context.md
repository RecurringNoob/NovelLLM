# Novel Writing Assistant — Implementation Context

> **Design Reference**: Technical Design v4  
> **Stack**: FastAPI · PostgreSQL 16 + pgvector · Redis 7 · React 18 + Vite (Phase 5+)  
> **Last Updated**: Phase 2 complete

---

## Phase 1 — Foundation (Complete ✅)

### What Was Built

#### Infrastructure
| File | Purpose |
|---|---|
| `docker-compose.yml` | Orchestrates Postgres (pgvector/pgvector:pg16), Redis 7, FastAPI. Hocuspocus commented out until Phase 6. |
| `.env.example` | All environment variables with placeholder values. Copy to `.env` and fill in `GEMINI_API_KEY`. |
| `backend/Dockerfile` | Python 3.12-slim, installs all deps including spaCy `en_core_web_sm` model. |
| `backend/requirements.txt` | Pinned dependencies for all phases (FastAPI, SQLAlchemy async, pgvector, Redis, Google Gen AI, spaCy, OTEL, etc.). |

#### FastAPI Application (`backend/app/`)
| Module | Purpose |
|---|---|
| `main.py` | App factory: lifespan (DB + Redis probe on startup), CORS, global exception handlers (BudgetExceeded → 403, InjectionDetected → 400, VersionConflict → 409), all routers mounted under `/api`. |
| `config.py` | Pydantic-settings `Settings` class. All values from `.env`. Includes `cors_origins_list` property. |
| `database.py` | Async SQLAlchemy engine (asyncpg, pool=10/20), `AsyncSessionLocal`, `Base`, `get_db()` dependency. |
| `dependencies.py` | `get_db` and `get_current_user`. **Phase 1 stub**: `get_current_user` returns a hardcoded dev UUID. **Phase 9**: Replace with real JWT extraction. |

#### Core Utilities (`backend/app/core/`)
| Module | Purpose |
|---|---|
| `exceptions.py` | All custom exceptions: `SafetyBlockError`, `InjectionDetectedError`, `BudgetExceededError`, `VersionConflictError`, `NERGuardTriggeredError`, `StageTimeoutError`, `InvalidStageOutputError`, `EntityNotFoundError`. |
| `redis_client.py` | Module-level Redis pool (`redis.asyncio`), `redis_ping()`, `close_redis_pool()`. |
| `logging.py` | Human-readable in dev; JSON lines in production (Loki-compatible). |

#### ORM Models (`backend/app/models/`) — 20 tables

| Model File | Tables | Key v4 Features |
|---|---|---|
| `project.py` | `projects`, `series` | `cost_spent_cents`, `cost_hard_limit_enabled`, `settings` JSONB with `maturity_level` |
| `chapter.py` | `chapters`, `chapter_state_snapshots`, `chapter_dependencies`, `prose_checkpoints` | `needs_revalidation` flag; `false_belief_resolutions` JSONB; `summary_embedding vector(768)` |
| `character.py` | `characters`, `character_presence` | `version` (OCC), `thread_ids` JSONB for ranking formula |
| `world.py` | `locations`, `plot_threads`, `outline_chapters`, `timeline_cells` | PlotThread status CHECK; `last_mentioned_chapter` for decay |
| `bible.py` | `bible_events`, `pending_bible_updates`, `generation_logs`, `prompt_templates`, `prompt_template_activations` | `source` CHECK on pending_updates; all v4 safety fields on generation_logs |
| `dialogue.py` | `dialogue_sessions` | `exchange_history` JSONB; `compressed_summary` for memory compression |
| `style.py` | `style_profiles` | `banned_words` JSONB; `tone_ceiling` |
| `analytics.py` | `chapter_analytics` | All measurable consistency metrics from Section 1 NFRs |
| `eval.py` | `eval_experiments`, `eval_results` | A/B variant buckets; rubric_scores JSONB; `passed` boolean (0.75 threshold) |

#### Alembic (`backend/alembic/`)
| File | Purpose |
|---|---|
| `alembic.ini` | Alembic config; DATABASE_URL overridden at runtime from env. |
| `alembic/env.py` | Async migration runner (asyncpg + `asyncio.run`); imports all models for autogenerate. |
| `alembic/versions/0001_initial_schema.py` | Creates `vector` extension + pgcrypto, all 20 tables, all CHECK constraints, all indexes, HNSW vector index. Full `downgrade()`. |

---

## Phase 2 — Self-Updating Bible + Integrity (Complete ✅)

### What Was Built

#### New Files

| File | Purpose |
|---|---|
| `backend/app/services/gemini_client.py` | Thin async Gemini wrapper: `GeminiClient.generate()` + `generate_json()` convenience method. SAFETY_SETTINGS_BY_LEVEL dict from TDD Section 2.2. Module-level `gemini` singleton. |
| `backend/app/services/bible_service.py` | Core bible mutation functions: `apply_pending_update()` (OCC), `reject_pending_update()`, `rollback_bible_to_event()` (compensating-event strategy), `record_bible_event()`, `write_chapter_snapshot()`, `load_chapter_snapshot()`. |
| `backend/app/services/stage5_service.py` | Stage 5 Delta Extractor: calls Gemini Flash JSON mode, enforces evidence-required guard on false belief resolutions, upserts chapter snapshots, queues `pending_bible_updates`, opens/closes plot threads, writes `GenerationLog`. |
| `backend/app/services/notification_service.py` | `notify_pending_badge()` — publishes pending update badge counts to Redis Pub/Sub channel `notelm:project:{id}:notifications`. Non-fatal on Redis failure. Phase 6 Hocuspocus will relay over WebSocket. |
| `backend/app/models/job.py` | `GenerationJob` ORM model: tracks async pipeline job state (queued → running → done/failed/safety_blocked), stores beats for the user edit gate, stores `partial_prose` + `blocked_at_checkpoint` for safety-block recovery. |
| `backend/alembic/versions/0002_generation_jobs.py` | Creates `generation_jobs` table with status CHECK constraint and all safety-recovery columns. |

#### Modified Files

| File | Changes |
|---|---|
| `backend/app/routers/bible.py` | **Fully implemented** from Phase 1 stubs: list/accept/reject/edit-and-accept pending updates, bible event audit log, rollback endpoint, manual Stage 5 trigger, chapter snapshot read endpoint. |
| `backend/app/routers/generation.py` | `/generate` now creates real `GenerationJob` DB records, performs budget check, and publishes to Redis Streams. `/continue-from-here` creates a job with `prepend_prose` intent. SSE stream polls job status and emits `job_status`, `beats`, `safety_block` events. New `beats_router` with `PUT /beats/{job_id}/confirm` for user edit gate. |
| `backend/app/schemas/bible.py` | `BibleRollbackRequest` now requires `project_id`. `PendingBibleUpdateRead` gains `user_edited_value` and `resolved_at`. `Stage5TriggerResponse` added. All Optional fields use `= None` default (Pydantic v2 compliant). |
| `backend/app/models/__init__.py` | `GenerationJob` registered for Alembic autogenerate. |
| `backend/app/main.py` | `beats_router` mounted at `/api/beats`. Version bumped to `0.2.0-phase2`. |

### Phase 2 API Endpoints (fully live)

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/projects/{id}/pending-updates` | List pending bible updates with status filter |
| `POST` | `/api/pending-updates/{id}/accept` | OCC accept → 409 on version conflict with three-way merge payload |
| `POST` | `/api/pending-updates/{id}/reject` | Reject pending update |
| `PUT` | `/api/pending-updates/{id}/edit-and-accept` | User edits then accepts (three-way merge) |
| `GET` | `/api/projects/{id}/bible-events` | Immutable event audit log |
| `POST` | `/api/bible/rollback` | Roll back entity to a prior snapshot via compensating event |
| `POST` | `/api/projects/{id}/chapters/{n}/stage5` | Manually trigger Stage 5 on existing prose |
| `GET` | `/api/projects/{id}/chapters/{n}/snapshot` | Read chapter state snapshot |
| `POST` | `/api/chapters/generate` | Create GenerationJob + Redis Streams enqueue |
| `POST` | `/api/chapters/continue-from-here` | Safety-block recovery job |
| `PUT` | `/api/beats/{job_id}/confirm` | Confirm/edit beats before Stage 3 (user edit gate) |
| `GET` | `/api/jobs/{job_id}/stream` | SSE job status stream |

### Key Phase 2 Decisions

#### OCC Strategy
`apply_pending_update()` in `bible_service.py` compares `entity_version_at_proposal` against the live entity version. On mismatch it raises `VersionConflictError` which the router maps to a structured 409 response containing `ai_saw_version`, `current_version`, and `ai_changes` — enough for the frontend three-way merge UI (Phase 5).

#### False Belief Resolution Guard
`stage5_service.py` drops any resolved false belief where the evidence string contains "implies" or "suggests" or is empty — matching the TDD Section 32 rule. Dropped resolutions are logged as warnings; the belief stays in `false_beliefs`.

#### Compensating Events for Rollback
`rollback_bible_to_event()` does not replay the full event log. Instead it restores `entity.data` from the stored `entity_snapshot` and writes a new `BibleEvent` with `source="rollback"`. This keeps the audit trail complete while being O(1) rather than O(N).

#### Notification Service
Publishes to Redis Pub/Sub — not HTTP. Phase 6 Hocuspocus subscribes to these channels and forwards them as WebSocket messages. Failures are non-fatal (badge degraded, core data intact).

---

## Key Architecture Decisions (cross-phase)

### Auth Stub
`get_current_user` returns a hardcoded dev UUID. **Phase 9** replaces with real JWT.

### pgvector Column
`chapters.summary_embedding = Vector(768)`. Created via raw SQL in migration to avoid type registration issues. HNSW index for ANN cosine search.

### OCC (Optimistic Concurrency Control)
`characters/locations/plot_threads.version` incremented on every update. `pending_bible_updates.entity_version_at_proposal` captures AI's view. Mismatch → 409 → frontend three-way merge.

### False Belief Resolution (v4)
`chapter_state_snapshots.false_belief_resolutions` JSONB. Stage 5 requires verbatim evidence. Stage 6 flags `false_belief_violation` if character acts against unresolved belief.

### Neon Postgres Configuration
To support Neon Serverless Postgres via a pooled connection, `app/database.py` includes `connect_args={"prepared_statement_cache_size": 0}` to disable `asyncpg` prepared statement caching, which otherwise conflicts with PgBouncer in transaction mode. The `DATABASE_URL` must also have `?sslmode=require` appended.

### Hocuspocus
Commented out in docker-compose. Activated Phase 6. Redis Pub/Sub bridge already in place via `notification_service.py`.

---

## How to Start (Development)

```bash
# Copy and populate .env
cp .env.example .env    # fill in GEMINI_API_KEY

# Start all services
docker compose up --build

# Run migrations (run BOTH in order)
docker compose exec api alembic upgrade head

# Verify
curl http://localhost:8000/health
# → {"status":"ok","db":"connected","redis":"connected","version":"0.2.0-phase2",...}

# Browse OpenAPI docs
# http://localhost:8000/docs
```

---

## Phase Roadmap

| Phase | Focus | Status |
|---|---|---|
| **1** | Foundation: Docker, DB models, FastAPI structure, CRUD | ✅ **Complete** |
| **2** | Self-Updating Bible: Stage 5, OCC apply logic, Notification Center, three-way merge | ✅ **Complete** |
| **3** | Context Intelligence: Decay, Lore-Check, Stage caching, Redis Streams, diff-based sync | ⏳ |
| **4** | Mature Content Pipeline: Genre vetting, literary framing, checkpoint streaming, safety recovery | ⏳ |
| **5** | Visual Modules: Timeline (dnd-kit), story map, outline, characters view, chapter reorder | ⏳ |
| **6** | Collaboration + Copilot: Yjs + Hocuspocus, scoped JWT, Tiptap, AI-as-collaborator | ⏳ |
| **7** | Dialogue, Style & Templates: Dialogue engine, style profiles, bootstrapping, series | ⏳ |
| **8** | Search, Exports & Quality: pgvector search, Shunn/EPUB3, Stage 6, NER guard, cost gauge | ⏳ |
| **9** | Observability, A/B & Launch: OTEL, Prometheus, Loki, A/B, CI eval gate, real auth | ⏳ |
