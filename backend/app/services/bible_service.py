"""
app/services/bible_service.py — Story Bible read / write helpers.

Shared by:
  - Stage 5 delta extractor (write pending updates + chapter snapshots)
  - Bible router (accept / reject / edit-and-accept / rollback)
  - Stage 1 context assembler (load bible snapshot — Phase 3)
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import VersionConflictError, EntityNotFoundError
from app.models.bible import BibleEvent, PendingBibleUpdate
from app.models.character import Character
from app.models.world import Location, PlotThread
from app.models.chapter import ChapterStateSnapshot

logger = logging.getLogger("notelm.bible")


# ── Entity resolver ────────────────────────────────────────────────────────────
async def _get_entity(db: AsyncSession, entity_type: str, entity_id: uuid.UUID):
    """Fetch a versioned entity by type and id. Raises EntityNotFoundError if missing."""
    model_map = {
        "character": Character,
        "location": Location,
        "plot_thread": PlotThread,
    }
    model = model_map.get(entity_type)
    if model is None:
        raise ValueError(f"Unknown entity_type: {entity_type!r}")
    obj = await db.get(model, entity_id)
    if obj is None:
        raise EntityNotFoundError(entity_type, str(entity_id))
    return obj


# ── Bible event recorder ───────────────────────────────────────────────────────
async def record_bible_event(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    chapter_number: int | None,
    source: str,
    entity_type: str | None,
    entity_id: uuid.UUID | None,
    changes: dict,
    entity_snapshot: dict | None = None,
) -> BibleEvent:
    """
    Append an immutable event to bible_events (event sourcing).
    Called after every accepted / edited-then-accepted pending update.
    """
    event = BibleEvent(
        project_id=project_id,
        chapter_number=chapter_number,
        source=source,
        entity_type=entity_type,
        entity_id=entity_id,
        changes=changes,
        entity_snapshot=entity_snapshot,
    )
    db.add(event)
    await db.flush()
    logger.info(
        "bible_event logged | project=%s chapter=%s source=%s entity_type=%s",
        project_id, chapter_number, source, entity_type,
    )
    return event


# ── OCC apply ──────────────────────────────────────────────────────────────────
async def apply_pending_update(
    db: AsyncSession,
    pending_id: uuid.UUID,
    *,
    edited_value: dict | None = None,
) -> PendingBibleUpdate:
    """
    Accept (or edit-then-accept) a pending bible update using OCC.

    Steps:
    1. Load the pending row — must be in status='pending'.
    2. Load the current entity version.
    3. Compare versions — raise VersionConflictError on mismatch.
    4. Apply changes to the entity (JSONB merge + version bump).
    5. Mark pending as 'accepted' (or 'edited') with resolved_at.
    6. Write a BibleEvent.
    7. Flush (caller commits via get_db()).

    Raises:
        EntityNotFoundError   — pending row or target entity not found.
        VersionConflictError  — OCC version mismatch.
    """
    # 1. Load pending
    result = await db.execute(
        select(PendingBibleUpdate).where(
            PendingBibleUpdate.id == pending_id,
            PendingBibleUpdate.status == "pending",
        )
    )
    pending = result.scalar_one_or_none()
    if pending is None:
        raise EntityNotFoundError("pending_bible_update", str(pending_id))

    changes = edited_value or pending.proposed_changes

    # 2 & 3. If the pending update targets a known versioned entity, check OCC
    if pending.entity_type and pending.entity_id and pending.entity_version_at_proposal is not None:
        entity = await _get_entity(db, pending.entity_type, pending.entity_id)
        if entity.version != pending.entity_version_at_proposal:
            raise VersionConflictError(
                entity_id=str(pending.entity_id),
                ai_saw_version=pending.entity_version_at_proposal,
                current_version=entity.version,
                ai_changes=changes,
            )

        # 4. Merge JSONB changes into entity.data and bump version
        if hasattr(entity, "data"):
            entity.data = {**entity.data, **changes}
        entity.version += 1
        snapshot = entity.data if hasattr(entity, "data") else {}
    else:
        # Entity-less updates (e.g. new artifact, new plot thread without an existing entity)
        entity = None
        snapshot = changes

    # 5. Mark pending resolved
    pending.status = "edited" if edited_value else "accepted"
    pending.user_edited_value = edited_value
    pending.resolved_at = datetime.now(timezone.utc)

    # 6. Record immutable event
    source_label = (
        "ai_delta_edited" if edited_value else "ai_delta_accepted"
    )
    await record_bible_event(
        db,
        project_id=pending.project_id,
        chapter_number=pending.chapter_number,
        source=source_label,
        entity_type=pending.entity_type,
        entity_id=pending.entity_id,
        changes=changes,
        entity_snapshot=snapshot,
    )
    await db.flush()
    return pending


async def reject_pending_update(db: AsyncSession, pending_id: uuid.UUID) -> PendingBibleUpdate:
    """Mark a pending update as rejected."""
    result = await db.execute(
        select(PendingBibleUpdate).where(
            PendingBibleUpdate.id == pending_id,
            PendingBibleUpdate.status == "pending",
        )
    )
    pending = result.scalar_one_or_none()
    if pending is None:
        raise EntityNotFoundError("pending_bible_update", str(pending_id))
    pending.status = "rejected"
    pending.resolved_at = datetime.now(timezone.utc)
    await db.flush()
    return pending


# ── Rollback ────────────────────────────────────────────────────────────────────
async def rollback_bible_to_event(
    db: AsyncSession,
    project_id: uuid.UUID,
    to_event_id: uuid.UUID,
) -> dict:
    """
    Roll back all entity changes made AFTER to_event_id by replaying the
    entity_snapshot of the target event back onto the entity.

    Strategy (simple snapshot revert):
    1. Load the target event — must belong to project.
    2. If the event has an entity_snapshot and targets a known entity,
       overwrite entity.data with the snapshot and decrement version.
    3. Mark all later events for the same entity as 'rolled_back' via
       a soft-delete approach (we insert a compensating BibleEvent).

    Note: Full replay-from-scratch is out of scope for Phase 2.
    The compensating-event approach is safe for the current data model.
    """
    # Load the target event
    result = await db.execute(
        select(BibleEvent).where(
            BibleEvent.id == to_event_id,
            BibleEvent.project_id == project_id,
        )
    )
    target_event = result.scalar_one_or_none()
    if target_event is None:
        raise EntityNotFoundError("bible_event", str(to_event_id))

    rolled_back_count = 0

    if (
        target_event.entity_snapshot
        and target_event.entity_type
        and target_event.entity_id
    ):
        try:
            entity = await _get_entity(db, target_event.entity_type, target_event.entity_id)
            old_data = dict(entity.data) if hasattr(entity, "data") else {}
            entity.data = target_event.entity_snapshot
            entity.version += 1  # bump so concurrent OCC checks don't mistakenly pass

            # Write compensating event
            await record_bible_event(
                db,
                project_id=project_id,
                chapter_number=target_event.chapter_number,
                source="rollback",
                entity_type=target_event.entity_type,
                entity_id=target_event.entity_id,
                changes={"__rollback_to_event": str(to_event_id)},
                entity_snapshot=target_event.entity_snapshot,
            )
            rolled_back_count += 1
        except (EntityNotFoundError, ValueError) as exc:
            logger.warning("Rollback could not restore entity: %s", exc)

    await db.flush()
    return {
        "rolled_back_to_event": str(to_event_id),
        "compensating_events_written": rolled_back_count,
    }


# ── Snapshot helpers ────────────────────────────────────────────────────────────
async def write_chapter_snapshot(
    db: AsyncSession,
    project_id: uuid.UUID,
    chapter_num: int,
    snapshot: dict,
) -> ChapterStateSnapshot:
    """
    Upsert a chapter state snapshot.
    Called by Stage 5 after each delta extraction.
    """
    result = await db.execute(
        select(ChapterStateSnapshot).where(
            ChapterStateSnapshot.project_id == project_id,
            ChapterStateSnapshot.chapter_number == chapter_num,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.party_status = snapshot.get("party_status", existing.party_status)
        existing.known_secrets = snapshot.get("known_secrets", existing.known_secrets)
        existing.false_beliefs = snapshot.get("false_beliefs", existing.false_beliefs)
        existing.false_belief_resolutions = snapshot.get(
            "false_belief_resolutions", existing.false_belief_resolutions
        )
        existing.world_conditions = snapshot.get("world_conditions", existing.world_conditions)
        row = existing
    else:
        row = ChapterStateSnapshot(
            project_id=project_id,
            chapter_number=chapter_num,
            party_status=snapshot.get("party_status", {}),
            known_secrets=snapshot.get("known_secrets", {}),
            false_beliefs=snapshot.get("false_beliefs", {}),
            false_belief_resolutions=snapshot.get("false_belief_resolutions", {}),
            world_conditions=snapshot.get("world_conditions", {}),
        )
        db.add(row)

    await db.flush()
    return row


async def load_chapter_snapshot(
    db: AsyncSession,
    project_id: uuid.UUID,
    chapter_num: int,
) -> ChapterStateSnapshot | None:
    """Load the snapshot for a specific chapter (or None if not yet created)."""
    result = await db.execute(
        select(ChapterStateSnapshot).where(
            ChapterStateSnapshot.project_id == project_id,
            ChapterStateSnapshot.chapter_number == chapter_num,
        )
    )
    return result.scalar_one_or_none()
