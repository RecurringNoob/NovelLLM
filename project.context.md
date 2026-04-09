# Novel Writing Assistant — Project Context

> **Stack**: FastAPI · PostgreSQL 16 + pgvector · Redis 7 · Pydantic v2 · SQLAlchemy 2.0 (Async)
> **Version**: `0.2.0-phase2`
> **Status**: Phase 1 ✅ Complete · Phase 2 ✅ Complete

---

## A. Phase 1 — Foundation

### Lifespan Events (`app/main.py`)

FastAPI's `@asynccontextmanager lifespan` handles both startup and shutdown in a single coroutine:

**Startup**:
1. Calls `redis_ping()` — logs a warning but does **not** crash if Redis is unreachable (degraded mode).
2. Opens a throwaway DB connection via `engine.connect()` and executes `SELECT 1` to verify PostgreSQL is reachable. Hard failure is logged but does not prevent the server from starting.

**Shutdown**:
1. `await close_redis_pool()` — drains the module-level Redis pool.
2. `await engine.dispose()` — closes the async SQLAlchemy engine pool.

Both probes happen before any HTTP traffic is accepted, ensuring the OpenAPI docs accurately reflect service health from the first request.

### CORS Setup

CORS is configured via `CORSMiddleware` immediately after the app is created:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,  # comma-separated env var
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

`cors_origins_list` is a `@property` on `Settings` that splits the `CORS_ORIGINS` env var on commas. Default: `http://localhost:5173,http://localhost:3000`.

### Global Exception Handlers

Three custom exceptions are caught at the app boundary and converted to structured JSON responses:

| Exception | HTTP Status | Use Case |
|---|---|---|
| `BudgetExceededError` | 403 | Hard cost limit hit |
| `InjectionDetectedError` | 400 | Prompt injection detected |
| `VersionConflictError` | 409 | OCC mismatch on bible accept |

### Database Schema — 21 Tables

Tables are grouped by domain. All use UUID primary keys and PostgreSQL-native types (JSONB, arrays, pgvector).

#### Projects & Series (2 tables)

| Table | Key Columns | Notes |
|---|---|---|
| `projects` | `settings JSONB`, `cost_spent_cents`, `cost_hard_limit_enabled` | Top-level novel entity; `settings` carries writing mode, maturity level, tone, POV, budget |
| `series` | `book_order JSONB`, `user_id` | Groups multiple projects (books) into a series |

#### Chapters & Narrative State (4 tables)

| Table | Key Columns | Notes |
|---|---|---|
| `chapters` | `content TEXT`, `summary_embedding vector(768)`, `needs_revalidation BOOL` | Prose content + HNSW-indexed embedding for semantic search; `needs_revalidation` triggers lazy consistency re-check |
| `chapter_state_snapshots` | `party_status`, `known_secrets`, `false_beliefs`, `false_belief_resolutions`, `world_conditions` (all JSONB) | Point-in-time narrative state at chapter end; composite PK `(project_id, chapter_number)` |
| `chapter_dependencies` | `dependency_type CHECK`, `depends_on_chapter` | Tracks causal chapter links for cascade revalidation (Phase 3) |
| `prose_checkpoints` | `job_id`, `checkpoint_num`, `content TEXT` | 500-word rolling checkpoint during Stage 3 streaming; safety-block recovery artifact |

#### Characters & Presence (2 tables)

| Table | Key Columns | Notes |
|---|---|---|
| `characters` | `data JSONB`, `version INT`, `thread_ids JSONB`, `last_mentioned_chapter` | OCC-versioned; `data` holds bio, arc_stage, goals, secrets; `thread_ids` used in context-ranking formula |
| `character_presence` | Composite PK `(character_id, chapter_id)` | Pivot table for Information Asymmetry Engine — determines which events a character could plausibly know |

#### World Building (4 tables)

| Table | Key Columns | Notes |
|---|---|---|
| `locations` | `data JSONB`, `version INT`, `last_mentioned_chapter` | OCC-versioned, decay-tracked |
| `plot_threads` | `status CHECK('active','dormant','resolved')`, `version INT`, `last_mentioned_chapter` | Stage 6 warns if active thread goes unmentioned for 3+ chapters |
| `outline_chapters` | `beats JSONB`, `template_slot TEXT` | AI-generated beat list; stores named plot template slot (e.g., `hero_journey:ordeal`) |
| `timeline_cells` | `chapter_number`, `plotline_id FK`, `tension_score`, `position` | Visual timeline grid cells for dnd-kit drag-drop (Phase 5) |

#### Story Bible (5 tables)

| Table | Key Columns | Notes |
|---|---|---|
| `bible_events` | `source`, `entity_type`, `entity_id`, `changes JSONB`, `entity_snapshot JSONB` | Immutable event log (event sourcing); `entity_snapshot` enables O(1) rollback |
| `pending_bible_updates` | `status CHECK`, `source CHECK`, `entity_version_at_proposal`, `user_edited_value JSONB` | AI-proposed changes awaiting human review; version field enables OCC |
| `generation_logs` | `stage`, `model`, `latency_ms`, `safety_blocked`, `blocked_twice`, `ner_guard_triggered` | Per-stage telemetry; joined to A/B experiments |
| `prompt_templates` | `template_text TEXT`, `is_active BOOL`, `version INT` | Versioned prompt store per stage |
| `prompt_template_activations` | `activated_at`, `deactivated_at`, `reason TEXT` | Rollback audit log for prompt activations |

#### Jobs (1 table)

| Table | Key Columns | Notes |
|---|---|---|
| `generation_jobs` | `status CHECK`, `stage`, `mode`, `beats JSONB`, `partial_prose TEXT`, `blocked_at_checkpoint` | Full pipeline job lifecycle; `beats` stored for user edit gate; `partial_prose` preserved on safety block |

#### Supporting (3 tables)

| Table | Key Columns | Notes |
|---|---|---|
| `dialogue_sessions` | `exchange_history JSONB`, `compressed_summary TEXT` | Dialogue engine session state; `compressed_summary` used when history exceeds token budget |
| `style_profiles` | `banned_words JSONB`, `tone_ceiling` | Style constraints applied by Stage 3 (Phase 7) |
| `chapter_analytics` | `consistency_score`, `knowledge_leakage_count`, `timeline_violation_count`, `false_belief_violation_count` | Stage 6 metrics; updated after each consistency run |

#### A/B Testing & Evaluation (2 tables)

| Table | Key Columns | Notes |
|---|---|---|
| `eval_experiments` | `variants JSONB`, `traffic_split FLOAT`, `status CHECK` | A/B experiment config; bucket assignment via `md5(project_id + experiment_id)` |
| `eval_results` | `rubric_scores JSONB`, `overall_score FLOAT`, `passed BOOL` | LLM-as-Judge output; CI gate threshold ≥ 0.75 |

---

## B. Phase 2 — Self-Updating Bible

### Optimistic Concurrency Control (OCC)

OCC prevents "stale-write" bugs where an AI proposed a change based on an outdated entity state while a human (or another AI run) had already mutated the entity.

**Version field usage**: Every versioned entity (`characters`, `locations`, `plot_threads`) carries an integer `version` field (default 1). When Stage 5 runs, it records the entity's current version in `pending_bible_updates.entity_version_at_proposal`.

**Conflict detection mechanism** (`bible_service.apply_pending_update`):

```python
if entity.version != pending.entity_version_at_proposal:
    raise VersionConflictError(
        entity_id=str(pending.entity_id),
        ai_saw_version=pending.entity_version_at_proposal,
        current_version=entity.version,
        ai_changes=changes,
    )
```

This check happens inside a database-level transaction. There is no window for a race condition between the `SELECT` and the `UPDATE` because the session holds an implicit row-level lock via `db.get()` → SQLAlchemy's identity map within the transaction.

**On success**: `entity.data` is merged with the proposed changes (JSONB merge), `entity.version` is incremented, the pending row is marked `accepted` (or `edited`), and an immutable `BibleEvent` is written.

**Retry/merge expectations**: On `VersionConflictError`, the router returns HTTP 409 with a structured payload:

```json
{
  "error": "version_conflict",
  "entity_id": "<uuid>",
  "ai_saw_version": 3,
  "current_version": 4,
  "ai_changes": { ... }
}
```

The frontend (Phase 5) uses this payload to render a **three-way merge UI**: original (AI's view), current (user's edits), and proposed (AI's changes). The user reconciles the conflict and calls `PUT /pending-updates/{id}/edit-and-accept` with the resolved `edited_value`.

### Stage 5 Delta Extraction

**What it does**: After Stage 3 prose is accepted, `run_stage5()` calls Gemini Flash in JSON mode (temperature 0.1) to extract a structured delta from the chapter text. This delta captures **everything that changed** in the narrative world during the chapter.

**How updates are derived**: The extracted delta contains seven keys:
- `global_state_updates` → updates to `known_secrets` and `party_status`
- `false_beliefs_resolved` → beliefs that were explicitly revealed in-scene
- `false_beliefs_introduced` → new misconceptions a character now holds
- `bible_additions` → new entities (character/location/artifact/event) to queue as pending bible updates
- `plot_threads_opened` / `plot_threads_closed` → thread lifecycle events
- `chapter_state_snapshot` → full state snapshot written to `chapter_state_snapshots`

Each `bible_addition` becomes a `PendingBibleUpdate` row with `source="ai_delta"`, awaiting human review in the Notification Center.

**How belief updates are validated** (Evidence Guard):

```python
evidence = resolution.get("evidence", "").strip()
if not evidence or "implies" in evidence.lower() or "suggests" in evidence.lower():
    # Drop the resolution — belief stays unresolved
    continue
```

A false belief resolution is rejected if:
1. The evidence is empty.
2. The evidence contains hedging language (`"implies"` or `"suggests"`).

Dropped resolutions are logged as warnings. The belief remains in `false_beliefs` until a future chapter provides explicit textual evidence. This prevents hallucinated revelations from corrupting the narrative state.

**Compensating Events for Rollback**: `rollback_bible_to_event()` restores `entity.data` from the `entity_snapshot` stored in the target `BibleEvent` and writes a new event with `source="rollback"`. This is O(1) — no log replay needed. The audit trail is preserved through the compensating event.

---

## C. How to Run the Project

### Prerequisites

- Docker Desktop (or Docker Engine + Compose plugin)
- A `.env` file with a Gemini API key

### Initial Setup

```bash
# 1. Clone and enter the project
git clone <repo-url> NoteLM
cd NoteLM

# 2. Create your .env file from the template
cp .env.example .env
# Edit .env and fill in:
#   GEMINI_API_KEY=your_key_here
# For Neon Postgres, set:
#   DATABASE_URL=postgresql+asyncpg://user:pass@host/db?sslmode=require
```

### Docker Setup

```bash
# Build and start all services (Postgres 16+pgvector, Redis 7, FastAPI)
docker compose up --build

# Run in detached mode (background)
docker compose up --build -d

# View logs
docker compose logs -f api
```

### Database Migrations

```bash
# Run both migrations in order (inside the running container)
docker compose exec api alembic upgrade head

# To verify migration status
docker compose exec api alembic current

# To generate a new migration after model changes
docker compose exec api alembic revision --autogenerate -m "describe_change"
```

### Running the Dev Server (without Docker)

```bash
cd backend

# Install dependencies
pip install -r requirements.txt

# Install spaCy model (required for NER guard, Phase 8)
python -m spacy download en_core_web_sm

# Set DATABASE_URL and REDIS_URL in your shell or .env
export DATABASE_URL="postgresql+asyncpg://notelm:notelm_secret@localhost:5432/notelm"
export REDIS_URL="redis://localhost:6379/0"
export GEMINI_API_KEY="your_key_here"

# Start the dev server with hot-reload
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Verification

```bash
# Health check
curl http://localhost:8000/health
# Expected: {"status":"ok","db":"connected","redis":"connected","environment":"development","version":"0.2.0-phase2"}

# OpenAPI interactive docs
# http://localhost:8000/docs

# ReDoc
# http://localhost:8000/redoc
```

### Neon Postgres Notes

When using Neon Serverless Postgres with a pooled connection (PgBouncer in transaction mode):

1. Set `DATABASE_URL` with `?sslmode=require` appended.
2. The engine already has `prepared_statement_cache_size=0` set — this **must** remain or asyncpg will fail with prepared statement conflicts.
3. Do **not** use `--pool-mode session` on the Neon connection string; transaction mode is required.

---

## Phase Roadmap

| Phase | Focus | Status |
|---|---|---|
| **1** | Foundation: Docker, DB models, FastAPI structure, CRUD | ✅ Complete |
| **2** | Self-Updating Bible: Stage 5, OCC apply logic, Notification Center, three-way merge | ✅ Complete |
| **3** | Context Intelligence: Decay, Lore-Check, Stage caching, Redis Streams, diff-based sync | ⏳ Planned |
| **4** | Mature Content Pipeline: Genre vetting, literary framing, checkpoint streaming, safety recovery | ⏳ Planned |
| **5** | Visual Modules: Timeline (dnd-kit), story map, outline, characters view, chapter reorder | ⏳ Planned |
| **6** | Collaboration + Copilot: Yjs + Hocuspocus, scoped JWT, Tiptap, AI-as-collaborator | ⏳ Planned |
| **7** | Dialogue, Style & Templates: Dialogue engine, style profiles, bootstrapping, series | ⏳ Planned |
| **8** | Search, Exports & Quality: pgvector search, Shunn/EPUB3, Stage 6, NER guard, cost gauge | ⏳ Planned |
| **9** | Observability, A/B & Launch: OTEL, Prometheus, Loki, A/B, CI eval gate, real auth | ⏳ Planned |
