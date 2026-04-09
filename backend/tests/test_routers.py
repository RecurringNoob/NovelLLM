"""
tests/test_routers.py — Router-level integration tests using httpx.AsyncClient.

Covers:
  1. Bible Router    — 200 success, 409 OCC conflict, 404 not found
  2. Generation Router — job creation, Redis Streams enqueue, budget enforcement
  3. SSE Stream Endpoint — mock Redis Pub/Sub, verify event sequence
  4. Beats Endpoint  — PUT /beats/{job_id}/confirm state update

All tests use:
  - httpx.AsyncClient (ASGI transport — no real HTTP port)
  - Dependency overrides for get_db and get_current_user
  - AsyncMock for GeminiClient
  - FakeRedis for Redis Streams

Run with:
    pytest backend/tests/test_routers.py -v
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.exceptions import EntityNotFoundError, VersionConflictError
from app.main import app
from app.dependencies import get_current_user, get_db

pytestmark = pytest.mark.asyncio

# ── Dev UUID used by the stub auth ──────────────────────────────────────────
DEV_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


# ─────────────────────────────────────────────────────────────────────────────
# Test client factory helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_dev_user():
    from app.dependencies import DevUser
    return DevUser(user_id=str(DEV_USER_ID))


def _make_async_client(db_override, redis_client=None):
    """
    Build an httpx.AsyncClient with dependency overrides.
    Returns an async context manager.
    """
    from app.core import redis_client as _rc

    async def _get_db_override():
        yield db_override

    async def _get_user_override():
        return _make_dev_user()

    app.dependency_overrides[get_db] = _get_db_override
    app.dependency_overrides[get_current_user] = _get_user_override

    if redis_client is not None:
        _rc._redis_pool = redis_client

    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://testserver")


def _reset_overrides():
    app.dependency_overrides.clear()


# ─────────────────────────────────────────────────────────────────────────────
# Shared mock builders
# ─────────────────────────────────────────────────────────────────────────────

def _pending_mock(
    *,
    status: str = "pending",
    entity_type: str = "character",
    entity_id: uuid.UUID | None = None,
    entity_version: int = 1,
    project_id: uuid.UUID | None = None,
) -> MagicMock:
    """Create a PendingBibleUpdate-like mock with all attributes set."""
    m = MagicMock()
    m.id = uuid.uuid4()
    m.project_id = project_id or uuid.uuid4()
    m.chapter_number = 1
    m.entity_type = entity_type
    m.entity_id = entity_id or uuid.uuid4()
    m.entity_version_at_proposal = entity_version
    m.proposed_changes = {"trait": "cunning"}
    m.status = status
    m.source = "ai_delta"
    m.user_edited_value = None
    m.created_at = datetime.now(timezone.utc)
    m.resolved_at = None
    return m


def _mock_db_for_pending(pending_obj) -> AsyncMock:
    """
    DB session that returns pending_obj on execute().scalar_one_or_none().
    Suitable for bible router tests.
    """
    db = AsyncMock()
    scalar = MagicMock()
    scalar.scalar_one_or_none = MagicMock(return_value=pending_obj)
    scalar.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[pending_obj])))
    db.execute = AsyncMock(return_value=scalar)
    db.flush = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.close = AsyncMock()
    return db


# ─────────────────────────────────────────────────────────────────────────────
# 1. Bible Router Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestBibleRouter:
    """Tests for bible.py router — OCC accept, reject, 404, 409 conflict."""

    @pytest_asyncio.fixture(autouse=True)
    async def cleanup(self):
        yield
        _reset_overrides()

    # ── 200 Success: accept pending update ────────────────────────────────

    async def test_accept_pending_update_200(self):
        """
        POST /api/pending-updates/{id}/accept should return 200 and the
        updated pending object when apply_pending_update succeeds.
        """
        pending = _pending_mock(status="accepted")
        db = _mock_db_for_pending(pending)

        with patch(
            "app.routers.bible.apply_pending_update",
            new=AsyncMock(return_value=pending),
        ), patch(
            "app.routers.bible.notify_pending_badge",
            new=AsyncMock(),
        ):
            async with _make_async_client(db) as client:
                resp = await client.post(f"/api/pending-updates/{pending.id}/accept")

        assert resp.status_code == 200, resp.text

    # ── 409 OCC Conflict ──────────────────────────────────────────────────

    async def test_accept_pending_update_409_on_version_conflict(self):
        """
        POST /api/pending-updates/{id}/accept should return 409 when
        apply_pending_update raises VersionConflictError.
        """
        entity_id = uuid.uuid4()
        pending = _pending_mock()
        db = _mock_db_for_pending(pending)

        with patch(
            "app.routers.bible.apply_pending_update",
            new=AsyncMock(
                side_effect=VersionConflictError(
                    entity_id=str(entity_id),
                    ai_saw_version=1,
                    current_version=3,
                    ai_changes={"trait": "cunning"},
                )
            ),
        ):
            async with _make_async_client(db) as client:
                resp = await client.post(f"/api/pending-updates/{pending.id}/accept")

        assert resp.status_code == 409
        body = resp.json()
        assert body["error"] == "version_conflict"
        assert body["ai_saw_version"] == 1
        assert body["current_version"] == 3

    async def test_edit_and_accept_409_on_version_conflict(self):
        """
        PUT /api/pending-updates/{id}/edit-and-accept should also return 409
        on version conflict.
        """
        entity_id = uuid.uuid4()
        pending = _pending_mock()
        db = _mock_db_for_pending(pending)

        with patch(
            "app.routers.bible.apply_pending_update",
            new=AsyncMock(
                side_effect=VersionConflictError(
                    entity_id=str(entity_id),
                    ai_saw_version=2,
                    current_version=5,
                    ai_changes={"trait": "fierce"},
                )
            ),
        ):
            async with _make_async_client(db) as client:
                resp = await client.put(
                    f"/api/pending-updates/{pending.id}/edit-and-accept",
                    json={"edited_value": {"trait": "fierce"}},
                )

        assert resp.status_code == 409
        body = resp.json()
        assert body["ai_saw_version"] == 2
        assert body["current_version"] == 5

    # ── 404 Not Found ─────────────────────────────────────────────────────

    async def test_accept_pending_update_404_when_not_found(self):
        """
        POST /api/pending-updates/{id}/accept should return 404 when
        apply_pending_update raises EntityNotFoundError.
        """
        db = _mock_db_for_pending(None)

        with patch(
            "app.routers.bible.apply_pending_update",
            new=AsyncMock(
                side_effect=EntityNotFoundError("pending_bible_update", str(uuid.uuid4()))
            ),
        ):
            async with _make_async_client(db) as client:
                resp = await client.post(f"/api/pending-updates/{uuid.uuid4()}/accept")

        assert resp.status_code == 404

    async def test_reject_pending_update_404_when_not_found(self):
        """
        POST /api/pending-updates/{id}/reject should return 404 when reject
        service raises EntityNotFoundError.
        """
        db = _mock_db_for_pending(None)
        with patch(
            "app.routers.bible.svc_reject",
            new=AsyncMock(
                side_effect=EntityNotFoundError("pending_bible_update", str(uuid.uuid4()))
            ),
        ):
            async with _make_async_client(db) as client:
                resp = await client.post(f"/api/pending-updates/{uuid.uuid4()}/reject")

        assert resp.status_code == 404

    async def test_reject_pending_update_200(self):
        """POST /api/pending-updates/{id}/reject should return 200 on success."""
        pending = _pending_mock(status="rejected")
        db = _mock_db_for_pending(pending)

        with patch(
            "app.routers.bible.svc_reject",
            new=AsyncMock(return_value=pending),
        ), patch(
            "app.routers.bible.notify_pending_badge",
            new=AsyncMock(),
        ):
            async with _make_async_client(db) as client:
                resp = await client.post(f"/api/pending-updates/{pending.id}/reject")

        assert resp.status_code == 200

    async def test_list_pending_updates_200(self):
        """GET /api/projects/{id}/pending-updates returns list of pending updates."""
        project_id = uuid.uuid4()
        pending = _pending_mock(project_id=project_id)
        db = _mock_db_for_pending(pending)

        async with _make_async_client(db) as client:
            resp = await client.get(f"/api/projects/{project_id}/pending-updates")

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Generation Router Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestGenerationRouter:
    """Tests for generation.py router — job creation, Redis, budget enforcement."""

    @pytest_asyncio.fixture(autouse=True)
    async def cleanup(self):
        yield
        _reset_overrides()

    def _make_project(
        self,
        *,
        project_id: uuid.UUID | None = None,
        cost_hard_limit_enabled: bool = False,
        cost_spent_cents: int = 0,
        budget_cents: int = 500,
    ) -> MagicMock:
        proj = MagicMock()
        proj.id = project_id or uuid.uuid4()
        proj.user_id = DEV_USER_ID
        proj.cost_hard_limit_enabled = cost_hard_limit_enabled
        proj.cost_spent_cents = cost_spent_cents
        proj.settings = {
            "maturity_level": "general",
            "writing_mode": "co-write",
            "cost_budget_cents": budget_cents,
        }
        return proj

    def _make_job(self, project_id: uuid.UUID) -> MagicMock:
        job = MagicMock()
        job.id = uuid.uuid4()
        job.project_id = project_id
        job.chapter_number = 1
        job.status = "queued"
        job.mode = "co-write"
        job.maturity_level = "general"
        return job

    def _make_db_with_project(self, project) -> AsyncMock:
        db = AsyncMock()
        db.get = AsyncMock(return_value=project)
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        db.close = AsyncMock()
        return db

    # ── Job creation ──────────────────────────────────────────────────────

    async def test_generate_creates_job_and_returns_queued(self, fake_redis):
        """POST /api/chapters/generate should return job_id with status=queued."""
        project_id = uuid.uuid4()
        project = self._make_project(project_id=project_id)
        job = self._make_job(project_id)
        db = self._make_db_with_project(project)

        with patch("app.routers.generation.GenerationJob") as MockJob:
            # The constructor returns our mock job
            MockJob.return_value = job

            async with _make_async_client(db, redis_client=fake_redis) as client:
                resp = await client.post(
                    "/api/chapters/generate",
                    json={
                        "project_id": str(project_id),
                        "chapter_number": 1,
                        "intent": {"writing_mode": "co-write"},
                    },
                )

        assert resp.status_code == 200
        body = resp.json()
        assert "job_id" in body
        assert body["status"] == "queued"

    async def test_generate_enqueues_to_redis_stream(self, fake_redis):
        """
        After job creation, the router must publish to Redis Streams 'job_stream'.
        """
        project_id = uuid.uuid4()
        project = self._make_project(project_id=project_id)
        job = self._make_job(project_id)
        db = self._make_db_with_project(project)

        with patch("app.routers.generation.GenerationJob") as MockJob:
            MockJob.return_value = job
            async with _make_async_client(db, redis_client=fake_redis) as client:
                await client.post(
                    "/api/chapters/generate",
                    json={
                        "project_id": str(project_id),
                        "chapter_number": 1,
                        "intent": {},
                    },
                )

        # Verify the stream has at least one entry
        stream_len = await fake_redis.xlen("job_stream")
        assert stream_len >= 1, "job_stream should have at least one entry after /generate"

    async def test_generate_returns_404_when_project_not_found(self, fake_redis):
        """POST /api/chapters/generate returns 404 if project not found."""
        db = AsyncMock()
        db.get = AsyncMock(return_value=None)  # Project not found
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        db.close = AsyncMock()

        async with _make_async_client(db, redis_client=fake_redis) as client:
            resp = await client.post(
                "/api/chapters/generate",
                json={
                    "project_id": str(uuid.uuid4()),
                    "chapter_number": 1,
                    "intent": {},
                },
            )

        assert resp.status_code == 404

    async def test_generate_enforces_budget_constraint(self, fake_redis):
        """
        POST /api/chapters/generate returns 403 when project has hit its hard cost limit.
        """
        project_id = uuid.uuid4()
        project = self._make_project(
            project_id=project_id,
            cost_hard_limit_enabled=True,
            cost_spent_cents=600,   # over budget
            budget_cents=500,
        )
        db = self._make_db_with_project(project)

        async with _make_async_client(db, redis_client=fake_redis) as client:
            resp = await client.post(
                "/api/chapters/generate",
                json={
                    "project_id": str(project_id),
                    "chapter_number": 1,
                    "intent": {},
                },
            )

        assert resp.status_code == 403
        body = resp.json()
        assert body["error"] == "budget_exceeded"
        assert "spent_cents" in body

    async def test_budget_not_enforced_when_limit_disabled(self, fake_redis):
        """When cost_hard_limit_enabled=False, generation proceeds even if spent > budget."""
        project_id = uuid.uuid4()
        project = self._make_project(
            project_id=project_id,
            cost_hard_limit_enabled=False,  # limit off
            cost_spent_cents=9999,
            budget_cents=100,
        )
        job = self._make_job(project_id)
        db = self._make_db_with_project(project)

        with patch("app.routers.generation.GenerationJob") as MockJob:
            MockJob.return_value = job
            async with _make_async_client(db, redis_client=fake_redis) as client:
                resp = await client.post(
                    "/api/chapters/generate",
                    json={
                        "project_id": str(project_id),
                        "chapter_number": 1,
                        "intent": {},
                    },
                )

        assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# 3. SSE Stream Endpoint Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestSSEStream:
    """
    Tests for GET /api/jobs/{job_id}/stream.

    The SSE endpoint polls the GenerationJob DB record and emits:
      - job_status events  (always)
      - beats event        (when stage='2' and status='queued' and beats present)
      - safety_block event (when status='safety_blocked')

    We mock the DB to return pre-configured job states and read the SSE response.
    """

    @pytest_asyncio.fixture(autouse=True)
    async def cleanup(self):
        yield
        _reset_overrides()

    def _make_job_mock(
        self,
        *,
        status: str = "done",
        stage: str | None = "3",
        mode: str = "co-write",
        beats: list | None = None,
        blocked_at_checkpoint: int | None = None,
        partial_prose: str | None = None,
    ) -> MagicMock:
        j = MagicMock()
        j.id = uuid.uuid4()
        j.status = status
        j.stage = stage
        j.mode = mode
        j.beats = beats
        j.blocked_at_checkpoint = blocked_at_checkpoint
        j.partial_prose = partial_prose
        return j

    def _make_db_for_job(self, job) -> AsyncMock:
        db = AsyncMock()
        scalar = MagicMock()
        scalar.scalar_one_or_none = MagicMock(return_value=job)
        db.execute = AsyncMock(return_value=scalar)
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        db.close = AsyncMock()
        return db

    async def _collect_sse_events(self, resp) -> list[dict]:
        """
        Parse raw SSE text into a list of {event, data} dicts.
        Works with streaming and non-streaming httpx responses.
        """
        text = resp.text
        events = []
        current_event: dict = {}
        for line in text.splitlines():
            if line.startswith("event:"):
                current_event["event"] = line[len("event:"):].strip()
            elif line.startswith("data:"):
                raw = line[len("data:"):].strip()
                try:
                    current_event["data"] = json.loads(raw)
                except json.JSONDecodeError:
                    current_event["data"] = raw
            elif line == "" and current_event:
                events.append(current_event)
                current_event = {}
        if current_event:
            events.append(current_event)
        return events

    async def test_sse_emits_job_status_event_for_done_job(self, fake_redis):
        """A done job should emit a job_status event with status='done'."""
        job = self._make_job_mock(status="done", stage="3")
        db = self._make_db_for_job(job)

        async with _make_async_client(db, redis_client=fake_redis) as client:
            resp = await client.get(f"/api/jobs/{job.id}/stream")

        assert resp.status_code == 200
        events = await self._collect_sse_events(resp)
        job_status_events = [e for e in events if e.get("event") == "job_status"]
        assert len(job_status_events) >= 1
        assert job_status_events[0]["data"]["status"] == "done"

    async def test_sse_emits_safety_block_event(self, fake_redis):
        """When job is safety_blocked, stream must emit a safety_block event."""
        job = self._make_job_mock(
            status="safety_blocked",
            stage=None,
            blocked_at_checkpoint=2,
            partial_prose="He walked through the door and " * 20,
        )
        db = self._make_db_for_job(job)

        async with _make_async_client(db, redis_client=fake_redis) as client:
            resp = await client.get(f"/api/jobs/{job.id}/stream")

        events = await self._collect_sse_events(resp)
        safety_events = [e for e in events if e.get("event") == "safety_block"]
        assert len(safety_events) >= 1
        safety_data = safety_events[0]["data"]
        assert safety_data["checkpoint"] == 2
        assert "recovery_options" in safety_data

    async def test_sse_emits_beats_event_when_awaiting_confirmation(self, fake_redis):
        """
        When job.status='queued' and job.stage='2' and beats are populated,
        the stream must emit a 'beats' SSE event.
        """
        beats = [
            {"beat": "Hero enters the cave", "tension": 6},
            {"beat": "Discovers the trap", "tension": 9},
        ]
        job = self._make_job_mock(status="queued", stage="2", beats=beats)
        # Return queued job once then done to stop the loop
        done_job = self._make_job_mock(status="done", stage="3")

        call_count = 0

        async def _execute_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            scalar = MagicMock()
            # First poll: awaiting beats. Second poll onwards: done to end stream.
            scalar.scalar_one_or_none = MagicMock(
                return_value=job if call_count == 1 else done_job
            )
            return scalar

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=_execute_side_effect)
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        db.close = AsyncMock()

        async with _make_async_client(db, redis_client=fake_redis) as client:
            resp = await client.get(f"/api/jobs/{job.id}/stream")

        events = await self._collect_sse_events(resp)
        beats_events = [e for e in events if e.get("event") == "beats"]
        assert len(beats_events) >= 1, "Expected at least one 'beats' SSE event"
        beats_data = beats_events[0]["data"]
        assert "beats" in beats_data
        assert len(beats_data["beats"]) == 2

    async def test_sse_emits_error_when_job_not_found(self, fake_redis):
        """When job_id doesn't exist, stream should emit an error event."""
        db = AsyncMock()
        scalar = MagicMock()
        scalar.scalar_one_or_none = MagicMock(return_value=None)
        db.execute = AsyncMock(return_value=scalar)
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        db.close = AsyncMock()

        async with _make_async_client(db, redis_client=fake_redis) as client:
            resp = await client.get(f"/api/jobs/{uuid.uuid4()}/stream")

        events = await self._collect_sse_events(resp)
        error_events = [e for e in events if e.get("event") == "error"]
        assert len(error_events) >= 1


# ─────────────────────────────────────────────────────────────────────────────
# 4. Beats Endpoint Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestBeatsEndpoint:
    """Tests for PUT /api/beats/{job_id}/confirm."""

    @pytest_asyncio.fixture(autouse=True)
    async def cleanup(self):
        yield
        _reset_overrides()

    def _make_job(self) -> MagicMock:
        j = MagicMock()
        j.id = uuid.uuid4()
        j.status = "queued"
        j.stage = "2"
        j.beats = None
        return j

    def _make_db_with_job(self, job) -> AsyncMock:
        db = AsyncMock()
        scalar = MagicMock()
        scalar.scalar_one_or_none = MagicMock(return_value=job)
        db.execute = AsyncMock(return_value=scalar)
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        db.close = AsyncMock()
        return db

    async def test_confirm_beats_updates_job_status_to_queued(self, fake_redis):
        """
        PUT /api/beats/{job_id}/confirm should:
          1. Accept the beats payload
          2. Set job.beats to the submitted list
          3. Set job.status = 'queued' (ready for Stage 3)
          4. Return 200 with beats_confirmed count
        """
        job = self._make_job()
        db = self._make_db_with_job(job)
        beats = [
            {"beat": "Lyra approaches the altar", "tension": 5},
            {"beat": "The guardian awakens", "tension": 8},
        ]

        async with _make_async_client(db, redis_client=fake_redis) as client:
            resp = await client.put(
                f"/api/beats/{job.id}/confirm",
                json=beats,
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["beats_confirmed"] == 2
        assert body["status"] == "queued"
        # Verify the mock job was updated
        assert job.beats == beats
        assert job.status == "queued"

    async def test_confirm_beats_enqueues_to_redis_stream(self, fake_redis):
        """
        After confirming beats, the endpoint must publish a resume_from_stage=3
        message to Redis Streams.
        """
        job = self._make_job()
        db = self._make_db_with_job(job)

        async with _make_async_client(db, redis_client=fake_redis) as client:
            await client.put(
                f"/api/beats/{job.id}/confirm",
                json=[{"beat": "test beat", "tension": 3}],
            )

        stream_len = await fake_redis.xlen("job_stream")
        assert stream_len >= 1, "beats confirmation must publish to job_stream"

    async def test_confirm_beats_returns_404_when_job_not_found(self, fake_redis):
        """PUT /api/beats/{job_id}/confirm returns 404 when job doesn't exist."""
        db = AsyncMock()
        scalar = MagicMock()
        scalar.scalar_one_or_none = MagicMock(return_value=None)
        db.execute = AsyncMock(return_value=scalar)
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        db.close = AsyncMock()

        async with _make_async_client(db, redis_client=fake_redis) as client:
            resp = await client.put(
                f"/api/beats/{uuid.uuid4()}/confirm",
                json=[{"beat": "ghost beat"}],
            )

        assert resp.status_code == 404

    async def test_confirm_beats_accepts_empty_list(self, fake_redis):
        """Empty beats list is valid — user might confirm 0 beats to skip Stage 2 gate."""
        job = self._make_job()
        db = self._make_db_with_job(job)

        async with _make_async_client(db, redis_client=fake_redis) as client:
            resp = await client.put(
                f"/api/beats/{job.id}/confirm",
                json=[],
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["beats_confirmed"] == 0
