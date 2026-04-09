"""
tests/test_bible_service.py — Unit tests for Phase 2 bible services.

Covers:
  1. OCC Conflict Test   — apply_pending_update raises VersionConflictError on version mismatch
  2. Evidence Guard Test — stage5_service rejects false belief resolutions containing
                           "implies" or "suggests" in the evidence string

All tests are async and fully isolated via unittest.mock.AsyncMock.
No real database calls are made — db sessions are mocked.

Run with:
    pytest backend/tests/test_bible_service.py -v
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from app.core.exceptions import VersionConflictError, EntityNotFoundError, InvalidStageOutputError
from app.services.bible_service import apply_pending_update

pytestmark = pytest.mark.asyncio


# ─────────────────────────────────────────────────────────────────────────────
# Helpers — lightweight fake ORM objects
# ─────────────────────────────────────────────────────────────────────────────

def _make_pending(
    *,
    pending_id: uuid.UUID | None = None,
    entity_type: str = "character",
    entity_id: uuid.UUID | None = None,
    entity_version_at_proposal: int = 1,
    proposed_changes: dict | None = None,
    project_id: uuid.UUID | None = None,
) -> MagicMock:
    """Create a mock PendingBibleUpdate ORM object."""
    m = MagicMock()
    m.id = pending_id or uuid.uuid4()
    m.entity_type = entity_type
    m.entity_id = entity_id or uuid.uuid4()
    m.entity_version_at_proposal = entity_version_at_proposal
    m.proposed_changes = proposed_changes or {"trait": "brave"}
    m.status = "pending"
    m.project_id = project_id or uuid.uuid4()
    m.chapter_number = 1
    m.user_edited_value = None
    m.resolved_at = None
    return m


def _make_entity(*, version: int = 1, data: dict | None = None) -> MagicMock:
    """Create a mock Character/Location/PlotThread ORM object."""
    e = MagicMock()
    e.version = version
    e.data = data or {"trait": "brave"}
    return e


def _make_db_session(pending_obj, entity_obj=None) -> AsyncMock:
    """
    Build a minimal async db session mock that:
      - execute() → returns pending on first call, entity on second
      - get()     → returns entity_obj directly
      - flush()   → no-op coroutine
      - add()     → no-op
    """
    db = AsyncMock()

    # scalar_one_or_none: first call returns pending, any subsequent returns entity
    scalar_mock = AsyncMock()
    scalar_mock.scalar_one_or_none = MagicMock(return_value=pending_obj)
    db.execute = AsyncMock(return_value=scalar_mock)

    if entity_obj is not None:
        db.get = AsyncMock(return_value=entity_obj)

    db.flush = AsyncMock()
    db.add = MagicMock()
    return db


# ─────────────────────────────────────────────────────────────────────────────
# OCC Conflict Test
# ─────────────────────────────────────────────────────────────────────────────

class TestApplyPendingUpdateOCC:
    """
    apply_pending_update should raise VersionConflictError when the entity's
    current version does not match entity_version_at_proposal captured by the AI.
    """

    async def test_version_conflict_raises_error(self):
        """
        Scenario: AI saw version 1 (at proposal time), user has since bumped it to 2.
        Expected: VersionConflictError is raised.
        """
        pending = _make_pending(entity_version_at_proposal=1)
        entity = _make_entity(version=2)  # current version is ahead

        db = _make_db_session(pending)

        with patch(
            "app.services.bible_service._get_entity", new=AsyncMock(return_value=entity)
        ):
            with pytest.raises(VersionConflictError) as exc_info:
                await apply_pending_update(db, pending.id)

        err = exc_info.value
        assert err.ai_saw_version == 1, "Error should report the AI's stale version"
        assert err.current_version == 2, "Error should report the live entity version"

    async def test_version_conflict_error_contains_entity_id(self):
        """
        The VersionConflictError must carry the entity_id so the router can
        include it in the 409 response for the three-way merge UI.
        """
        entity_id = uuid.uuid4()
        pending = _make_pending(entity_id=entity_id, entity_version_at_proposal=3)
        entity = _make_entity(version=5)

        db = _make_db_session(pending)

        with patch("app.services.bible_service._get_entity", new=AsyncMock(return_value=entity)):
            with pytest.raises(VersionConflictError) as exc_info:
                await apply_pending_update(db, pending.id)

        assert str(exc_info.value.entity_id) == str(entity_id)

    async def test_version_conflict_error_contains_ai_changes(self):
        """
        ai_changes in the error must equal proposed_changes from the pending row,
        enabling the frontend to display what the AI wanted to apply.
        """
        proposed = {"alignment": "chaotic_good", "arc_stage": "resolution"}
        pending = _make_pending(
            entity_version_at_proposal=2,
            proposed_changes=proposed,
        )
        entity = _make_entity(version=9)

        db = _make_db_session(pending)

        with patch("app.services.bible_service._get_entity", new=AsyncMock(return_value=entity)):
            with pytest.raises(VersionConflictError) as exc_info:
                await apply_pending_update(db, pending.id)

        assert exc_info.value.ai_changes == proposed

    async def test_no_conflict_when_versions_match(self):
        """
        When entity.version == entity_version_at_proposal, apply should succeed
        (version conflict must NOT be raised).
        """
        proposed = {"trait": "cunning"}
        pending = _make_pending(
            entity_version_at_proposal=3,
            proposed_changes=proposed,
        )
        entity = _make_entity(version=3, data={"trait": "brave"})

        db = _make_db_session(pending)

        with patch("app.services.bible_service._get_entity", new=AsyncMock(return_value=entity)):
            # record_bible_event is also called; mock it to avoid further DB calls
            with patch("app.services.bible_service.record_bible_event", new=AsyncMock()):
                result = await apply_pending_update(db, pending.id)

        assert result is pending
        assert entity.version == 4, "Entity version must be incremented on successful apply"
        assert pending.status == "accepted"

    async def test_entity_not_found_raises_error(self):
        """
        If the pending row does not exist (status != pending or ID wrong),
        apply_pending_update must raise EntityNotFoundError.
        """
        db = AsyncMock()
        scalar_mock = MagicMock()
        scalar_mock.scalar_one_or_none = MagicMock(return_value=None)
        db.execute = AsyncMock(return_value=scalar_mock)

        with pytest.raises(EntityNotFoundError):
            await apply_pending_update(db, uuid.uuid4())

    async def test_entity_less_update_no_occ_check(self):
        """
        Pending updates without entity_type/entity_id (e.g. new artifacts)
        must be applied without OCC version check.
        """
        pending = _make_pending(entity_version_at_proposal=1)
        pending.entity_type = None  # entity-less
        pending.entity_id = None
        pending.entity_version_at_proposal = None

        db = _make_db_session(pending)

        with patch("app.services.bible_service.record_bible_event", new=AsyncMock()):
            # Must not raise — no entity to check OCC against
            result = await apply_pending_update(db, pending.id)

        assert result is pending
        assert pending.status == "accepted"

    async def test_edited_value_uses_user_changes_in_error(self):
        """
        When edit-and-accept is called with an edited_value and a version conflict
        occurs, the VersionConflictError.ai_changes must reflect the edited_value,
        not the original proposed_changes.
        """
        original = {"trait": "calm"}
        edited = {"trait": "fierce", "arc_stage": "crisis"}
        pending = _make_pending(entity_version_at_proposal=1, proposed_changes=original)
        entity = _make_entity(version=2)

        db = _make_db_session(pending)

        with patch("app.services.bible_service._get_entity", new=AsyncMock(return_value=entity)):
            with pytest.raises(VersionConflictError) as exc_info:
                await apply_pending_update(db, pending.id, edited_value=edited)

        assert exc_info.value.ai_changes == edited


# ─────────────────────────────────────────────────────────────────────────────
# Evidence Guard Tests (Stage 5)
# ─────────────────────────────────────────────────────────────────────────────

# Minimal valid Stage 5 delta that passes all required-key checks
def _make_valid_delta(false_beliefs_resolved: dict) -> dict:
    return {
        "global_state_updates": {},
        "false_beliefs_resolved": false_beliefs_resolved,
        "false_beliefs_introduced": {},
        "bible_additions": [],
        "plot_threads_opened": [],
        "plot_threads_closed": [],
        "chapter_state_snapshot": {
            "party_status": {},
            "known_secrets": {},
            "false_beliefs": {},
            "false_belief_resolutions": {},
            "world_conditions": {},
        },
    }


class TestStage5EvidenceGuard:
    """
    run_stage5 must reject false belief resolutions that:
      - Have empty evidence strings
      - Contain "implies" (case-insensitive)
      - Contain "suggests" (case-insensitive)

    Valid verbatim evidence must be kept.
    """

    def _make_db(self) -> AsyncMock:
        """Minimal db mock for stage5 — flush + add only."""
        db = AsyncMock()
        db.flush = AsyncMock()
        db.add = MagicMock()
        db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )
        return db

    async def _run(self, delta: dict, db=None) -> dict:
        """
        Call run_stage5 with Gemini mocked to return the given delta.
        Returns the output delta dict.
        """
        from app.services.stage5_service import run_stage5

        db = db or self._make_db()

        with patch("app.services.stage5_service.gemini") as mock_gemini:
            mock_gemini.generate_json = AsyncMock(return_value=delta)
            # write_chapter_snapshot writes to DB — mock it
            with patch(
                "app.services.stage5_service.write_chapter_snapshot",
                new=AsyncMock(),
            ):
                result = await run_stage5(
                    db,
                    project_id=uuid.uuid4(),
                    chapter_number=3,
                    prose="The scene was tense.",
                    prior_snapshot={},
                    job_id=uuid.uuid4(),
                    maturity_level="general",
                )
        return result

    # ── Rejection cases ────────────────────────────────────────────────────

    async def test_rejects_empty_evidence(self):
        """Empty evidence string → resolution dropped."""
        delta = _make_valid_delta({
            "Lyra": {
                "Lyra believes Kael is loyal": {
                    "evidence": ""
                }
            }
        })
        result = await self._run(delta)
        assert result["false_beliefs_resolved"] == {}, (
            "Empty evidence must be rejected — belief stays unresolved"
        )

    async def test_rejects_evidence_with_implies(self):
        """Evidence containing 'implies' → resolution dropped."""
        delta = _make_valid_delta({
            "Kael": {
                "Kael thinks the alliance holds": {
                    "evidence": "The scene implies Kael now knows the alliance is broken."
                }
            }
        })
        result = await self._run(delta)
        assert "Kael" not in result["false_beliefs_resolved"]

    async def test_rejects_evidence_with_suggests(self):
        """Evidence containing 'suggests' → resolution dropped."""
        delta = _make_valid_delta({
            "Mira": {
                "Mira does not know Soren survived": {
                    "evidence": "Mira's reaction suggests she is now aware Soren is alive."
                }
            }
        })
        result = await self._run(delta)
        assert result["false_beliefs_resolved"] == {}

    async def test_rejects_implies_case_insensitive(self):
        """'Implies' (capital I) must also be rejected."""
        delta = _make_valid_delta({
            "Aria": {
                "Aria falsely assumes the key is missing": {
                    "evidence": "The open chest Implies the key has been taken."
                }
            }
        })
        result = await self._run(delta)
        assert result["false_beliefs_resolved"] == {}

    async def test_rejects_suggests_uppercase(self):
        """'SUGGESTS' (fully uppercase) must also be rejected."""
        delta = _make_valid_delta({
            "Torin": {
                "Torin does not know the queen is dead": {
                    "evidence": "His trembling hands SUGGESTS he has already heard the news."
                }
            }
        })
        result = await self._run(delta)
        assert result["false_beliefs_resolved"] == {}

    # ── Acceptance cases ───────────────────────────────────────────────────

    async def test_accepts_verbatim_evidence(self):
        """Explicit, verbatim quote → resolution kept."""
        delta = _make_valid_delta({
            "Lyra": {
                "Lyra believes the city is safe": {
                    "evidence": "Lyra gasps: 'The city has fallen. I can see the fires from here.'"
                }
            }
        })
        result = await self._run(delta)
        assert "Lyra" in result["false_beliefs_resolved"]
        assert "Lyra believes the city is safe" in result["false_beliefs_resolved"]["Lyra"]

    async def test_accepts_close_paraphrase_without_hedge_words(self):
        """A paraphrase without hedging words ('implies'/'suggests') is accepted."""
        delta = _make_valid_delta({
            "Daven": {
                "Daven thinks the portal is still active": {
                    "evidence": "The portal collapses before Daven's eyes, scattering ash across the floor."
                }
            }
        })
        result = await self._run(delta)
        assert "Daven" in result["false_beliefs_resolved"]

    async def test_partial_rejection_keeps_valid_resolutions(self):
        """
        When one character's resolution is valid and another's is hedged,
        only the hedged one must be dropped.
        """
        delta = _make_valid_delta({
            "Lyra": {
                "Lyra thinks Kael is dead": {
                    "evidence": "Kael steps into the torchlight. 'You thought I was gone,' he says."
                }
            },
            "Kael": {
                "Kael does not know about the betrayal": {
                    "evidence": "The scene implies Kael now suspects the truth."
                }
            },
        })
        result = await self._run(delta)
        assert "Lyra" in result["false_beliefs_resolved"], "Valid resolution must be kept"
        assert "Kael" not in result["false_beliefs_resolved"], "Hedged resolution must be dropped"

    async def test_missing_keys_raises_invalid_stage_output(self):
        """
        If Gemini returns a delta missing required top-level keys,
        run_stage5 must raise InvalidStageOutputError.
        """
        bad_delta = {
            "false_beliefs_resolved": {},
            # missing: global_state_updates, false_beliefs_introduced, etc.
        }
        from app.core.exceptions import InvalidStageOutputError
        from app.services.stage5_service import run_stage5

        db = self._make_db()
        with patch("app.services.stage5_service.gemini") as mock_gemini:
            mock_gemini.generate_json = AsyncMock(return_value=bad_delta)
            with pytest.raises(InvalidStageOutputError):
                await run_stage5(
                    db,
                    project_id=uuid.uuid4(),
                    chapter_number=1,
                    prose="Test prose",
                    prior_snapshot={},
                    job_id=uuid.uuid4(),
                )
