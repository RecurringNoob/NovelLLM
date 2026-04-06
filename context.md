# Novel Writing Assistant — Implementation Context

> **Design Reference**: Technical Design v4  
> **Stack**: FastAPI · PostgreSQL 16 + pgvector · Redis 7 · React 18 + Vite (Phase 5+)  
> **Last Updated**: Phase 1 complete

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
| `exceptions.py` | All custom exceptions: `SafetyBlockError`, `InjectionDetectedError`, `BudgetExceededError`, `VersionConflictError`, `NERGuardTriggeredError`, `StageTimeoutError`, `InvalidStageOutputError`. |
| `redis_client.py` | Module-level Redis pool (`redis.asyncio`), `redis_ping()`, `close_redis_pool()`. |
| `logging.py` | Human-readable in dev; JSON lines in production (Loki-compatible). Silences noisy SQLAlchemy/uvicorn loggers. |

#### ORM Models (`backend/app/models/`)

All tables from **Section 5** of the Technical Design v4 plus referenced supporting tables:

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

**Total: 20 tables**

#### Pydantic Schemas (`backend/app/schemas/`)

| Schema File | Covers |
|---|---|
| `common.py` | `APIResponse[T]`, `NotImplementedResponse`, `HealthResponse`, `ORMBase` |
| `project.py` | `ProjectCreate/Update/Read`, `ProjectSettings`, `ProjectCostRead`, `SeriesCreate/Read` |
| `chapter.py` | `ChapterCreate/Update/Read/ReadFull`, `GenerationRequest`, `GenerationJobResponse`, `AutocompleteRequest`, `ContinueFromHereRequest`, `AutoFixWarningRequest/Response`, `ReorderChaptersRequest/Response`, `BibleSyncRequest`, `Range` |
| `character.py` | `CharacterCreate/Update/Read`, `CharacterDeepenRequest` |
| `world.py` | `LocationCreate/Read`, `PlotThreadCreate/Update/Read` (with `stale_warning`), `TimelineCellCreate/Read`, `ApplyTemplateRequest` |
| `bible.py` | `PendingBibleUpdateRead`, `AcceptPendingUpdateRequest`, `EditAndAcceptRequest`, `BibleRollbackRequest`, `PromptTemplateRead`, `PromptRollbackRequest`, `GenerationLogRead` |

#### API Routers (`backend/app/routers/`)

All endpoints from **Section 38** mapped to the correct HTTP method + path:

| Router | Phase 1 Status | Stubbed For |
|---|---|---|
| `projects.py` | **Full CRUD + cost endpoint** ✅ | Timeline, story-map, reorder → Phase 5 |
| `chapters.py` | **Full CRUD** ✅ | Bible-sync, auto-fix → Phases 3/4 |
| `characters.py` | **Full CRUD** ✅ | Deepen → Phase 7 |
| `plot_threads.py` | **Full CRUD** ✅ | stale_warning computation → Phase 5 |
| `generation.py` | Stubbed (correct signatures) | Full pipeline → Phase 1 (worker) |
| `bible.py` | Stubbed | Pending updates, rollback → Phase 2 |
| `dialogue.py` | Stubbed | Phase 7 |
| `search.py` | Stubbed | Phase 8 |
| `exports.py` | Stubbed | Phase 8 |
| `bootstrap.py` | Stubbed | Phase 7 |
| `admin.py` | Stubbed | Phase 9 |

#### Alembic (`backend/alembic/`)
| File | Purpose |
|---|---|
| `alembic.ini` | Alembic config; DATABASE_URL overridden at runtime from env. |
| `alembic/env.py` | Async migration runner (asyncpg + `asyncio.run`); imports all models for autogenerate. |
| `alembic/versions/0001_initial_schema.py` | Creates `vector` extension + pgcrypto, all 20 tables in FK-dependency order, all CHECK constraints, all indexes, HNSW vector index on `chapters.summary_embedding`. Full `downgrade()`. |

---

## Key Architecture Decisions (Phase 1)

### Auth Stub
`get_current_user` returns a hardcoded dev UUID (`00000000-0000-0000-0000-000000000001`). All DB rows have `user_id` columns ready. **Phase 9** replaces this with real JWT Bearer token extraction and DB lookup.

### pgvector Column
`chapters.summary_embedding` uses `Vector(768)` from the `pgvector` Python package. The Alembic migration creates it via raw SQL (`ALTER TABLE chapters ADD COLUMN summary_embedding vector(768)`) to avoid SQLAlchemy type registration issues. An HNSW index is created for approximate nearest-neighbour cosine search.

### OCC (Optimistic Concurrency Control)
`characters.version` and `locations.version` and `plot_threads.version` are incremented on every update. `pending_bible_updates.entity_version_at_proposal` captures the version seen by the AI. On accept, a mismatch raises `VersionConflictError` (409) — the UI shows a three-way merge.

### Hocuspocus
Commented out in `docker-compose.yml`. Activated in **Phase 6** when the Node.js service and scoped JWT generation are implemented.

### False Belief Resolution (v4)
`chapter_state_snapshots.false_belief_resolutions` JSONB stores verbatim evidence quotes. Stage 5 is required to provide evidence to resolve a belief. Stage 6 flags `false_belief_violation` if a character acts against an unresolved belief. See Sections 32 and 8.

---

## How to Start (Development)

```bash
# 1. Copy and populate .env
cp .env.example .env
# Edit GEMINI_API_KEY in .env

# 2. Start all services
docker compose up --build

# 3. Run migrations (in a second terminal)
docker compose exec api alembic upgrade head

# 4. Verify
curl http://localhost:8000/health
# → {"status":"ok","db":"connected","redis":"connected","environment":"development"}

# 5. Browse OpenAPI docs
# http://localhost:8000/docs
```

---

## Phase Roadmap

| Phase | Focus | Status |
|---|---|---|
| **1** | Foundation: Docker, DB models, FastAPI structure, CRUD | ✅ **Complete** |
| **2** | Self-Updating Bible: Stage 5, OCC apply logic, Notification Center, three-way merge | ⏳ Pending confirmation |
| **3** | Context Intelligence: Decay, Lore-Check, Stage caching, Redis Streams, diff-based sync | ⏳ |
| **4** | Mature Content Pipeline: Genre vetting, literary framing, checkpoint streaming, safety recovery | ⏳ |
| **5** | Visual Modules: Timeline (dnd-kit), story map, outline, characters view, chapter reorder | ⏳ |
| **6** | Collaboration + Copilot: Yjs + Hocuspocus, scoped JWT, Tiptap, AI-as-collaborator | ⏳ |
| **7** | Dialogue, Style & Templates: Dialogue engine, style profiles, bootstrapping, series | ⏳ |
| **8** | Search, Exports & Quality: pgvector search, Shunn/EPUB3, Stage 6, NER guard, cost gauge | ⏳ |
| **9** | Observability, A/B & Launch: OTEL, Prometheus, Loki, A/B, CI eval gate, real auth | ⏳ |
