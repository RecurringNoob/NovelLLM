"""
app/services/stage5_service.py — Stage 5: Delta Extractor

Runs after Stage 3 prose is accepted. Extracts:
  - global_state_updates   → known_secrets, party_status
  - false_beliefs_resolved → with required evidence quote (TDD Section 32)
  - false_beliefs_introduced
  - bible_additions        → new entities to queue as pending_bible_updates
  - plot_threads_opened / closed
  - chapter_state_snapshot → upserted in DB

Model: Flash · temp 0.1 · JSON mode
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bible import GenerationLog, PendingBibleUpdate
from app.models.world import PlotThread
from app.services.bible_service import write_chapter_snapshot
from app.services.gemini_client import gemini

logger = logging.getLogger("notelm.stage5")

# ── Stage 5 system prompt ──────────────────────────────────────────────────────
STAGE5_SYSTEM_PROMPT = """
You are a story-bible delta extractor for a novel writing assistant.

Analyse the provided chapter prose and produce a JSON object with the following
exact schema. Output ONLY valid JSON — no markdown fences, no commentary.

SCHEMA:
{
  "global_state_updates": {
    "known_secrets": { "<character>": ["append: <secret>"] },
    "party_status":  { "<character>": "<new status>" }
  },
  "false_beliefs_resolved": {
    "<character>": {
      "<exact false belief text>": {
        "evidence": "<verbatim or close-paraphrase quote from prose showing the revelation>"
      }
    }
  },
  "false_beliefs_introduced": {
    "<character>": ["<new false belief text>"]
  },
  "bible_additions": [
    { "type": "character|location|artifact|event", "data": { ... } }
  ],
  "plot_threads_opened":  ["<thread title>"],
  "plot_threads_closed":  ["<thread title>"],
  "chapter_state_snapshot": {
    "party_status":              { "<character>": "<status>" },
    "known_secrets":             { "<character>": ["<secret>"] },
    "false_beliefs":             { "<character>": ["<belief>"] },
    "false_belief_resolutions":  {
      "<character>": {
        "<belief text>": {
          "resolved_in_chapter": <int>,
          "evidence": "<quote>"
        }
      }
    },
    "world_conditions": { "<condition>": "<state>" }
  }
}

CRITICAL RULE — FALSE BELIEF RESOLUTION:
A false belief may ONLY be placed in false_beliefs_resolved if you can provide
verbatim (or close paraphrase) textual evidence from the prose that constitutes
an explicit in-scene revelation observable to the reader.

VALID:   "evidence": "Lyra says 'I know what you did, Kael. I've always known.'"
INVALID: "evidence": "The scene implies Lyra now knows"
INVALID: "evidence": "Kael's reaction suggests he realises"

If no explicit evidence exists, do NOT include the belief in false_beliefs_resolved.
Leave it in false_beliefs and output nothing for that belief in false_beliefs_resolved.

Return an empty object/array for any key that has no new information.
"""


def _build_stage5_prompt(
    chapter_num: int,
    prose: str,
    prior_snapshot: dict,
    prior_false_beliefs: dict,
) -> str:
    """Assemble the full Stage 5 prompt."""
    return f"""{STAGE5_SYSTEM_PROMPT}

=== CHAPTER {chapter_num} PROSE ===
{prose[:15000]}

=== PRIOR STATE (end of chapter {chapter_num - 1}) ===
Party status:    {json.dumps(prior_snapshot.get('party_status', {}))}
Known secrets:   {json.dumps(prior_snapshot.get('known_secrets', {}))}
False beliefs:   {json.dumps(prior_false_beliefs)}
World conditions: {json.dumps(prior_snapshot.get('world_conditions', {}))}

Produce the delta JSON now:
"""


async def run_stage5(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    chapter_number: int,
    prose: str,
    prior_snapshot: dict,
    job_id: uuid.UUID,
    maturity_level: str = "general",
) -> dict[str, Any]:
    """
    Execute Stage 5: Delta Extraction.

    Returns the parsed delta dict. Side effects:
    - Upserts chapter_state_snapshot
    - Queues new pending_bible_updates (bible_additions)
    - Opens/closes plot threads
    - Writes a GenerationLog row

    Raises InvalidStageOutputError if Gemini returns malformed JSON.
    """
    import time
    from app.core.exceptions import InvalidStageOutputError

    prior_false_beliefs = prior_snapshot.get("false_beliefs", {})
    prompt = _build_stage5_prompt(chapter_number, prose, prior_snapshot, prior_false_beliefs)

    start = time.monotonic()
    try:
        delta = await gemini.generate_json(
            prompt,
            model="flash",
            temperature=0.1,
            max_tokens=4096,
        )
    except (json.JSONDecodeError, Exception) as exc:
        logger.error("Stage 5 Gemini error: %s", exc)
        raise InvalidStageOutputError("5", str(exc))
    latency_ms = int((time.monotonic() - start) * 1000)

    # ── Validate required keys ───────────────────────────────────────
    required = {
        "global_state_updates", "false_beliefs_resolved",
        "false_beliefs_introduced", "bible_additions",
        "plot_threads_opened", "plot_threads_closed",
        "chapter_state_snapshot",
    }
    missing = required - set(delta.keys())
    if missing:
        raise InvalidStageOutputError("5", f"Missing keys: {missing}")

    # ── Guard: false belief resolution must have evidence ───────────
    cleaned_resolutions: dict = {}
    for char, beliefs in delta.get("false_beliefs_resolved", {}).items():
        char_resolutions: dict = {}
        for belief_text, resolution in beliefs.items():
            evidence = resolution.get("evidence", "").strip()
            if not evidence or "implies" in evidence.lower() or "suggests" in evidence.lower():
                logger.warning(
                    "Stage 5: false belief resolution for '%s'/'%s' rejected — "
                    "evidence missing or inference-only.",
                    char, belief_text,
                )
                # Drop this resolution; belief stays unresolved
                continue
            char_resolutions[belief_text] = {
                "resolved_in_chapter": chapter_number,
                "evidence": evidence,
            }
        if char_resolutions:
            cleaned_resolutions[char] = char_resolutions

    delta["false_beliefs_resolved"] = cleaned_resolutions

    # ── Update chapter_state_snapshot ────────────────────────────────
    snapshot_data = delta.get("chapter_state_snapshot", {})
    # Merge cleaned resolutions into snapshot
    snap_resolutions = snapshot_data.get("false_belief_resolutions", {})
    for char, resolutions in cleaned_resolutions.items():
        snap_resolutions.setdefault(char, {}).update(resolutions)
    snapshot_data["false_belief_resolutions"] = snap_resolutions

    await write_chapter_snapshot(db, project_id, chapter_number, snapshot_data)

    # ── Queue pending bible updates for bible_additions ───────────────
    for addition in delta.get("bible_additions", []):
        pending = PendingBibleUpdate(
            project_id=project_id,
            chapter_number=chapter_number,
            entity_type=addition.get("type"),
            proposed_changes=addition.get("data", {}),
            source="ai_delta",
            source_job_id=job_id,
            status="pending",
        )
        db.add(pending)

    # ── Open / close plot threads ────────────────────────────────────
    for thread_title in delta.get("plot_threads_opened", []):
        result = await db.execute(
            select(PlotThread).where(
                PlotThread.project_id == project_id,
                PlotThread.title == thread_title,
            )
        )
        thread = result.scalar_one_or_none()
        if thread is None:
            thread = PlotThread(
                project_id=project_id,
                title=thread_title,
                status="active",
                last_mentioned_chapter=chapter_number,
            )
            db.add(thread)
        else:
            thread.status = "active"
            thread.last_mentioned_chapter = chapter_number

    for thread_title in delta.get("plot_threads_closed", []):
        result = await db.execute(
            select(PlotThread).where(
                PlotThread.project_id == project_id,
                PlotThread.title == thread_title,
            )
        )
        thread = result.scalar_one_or_none()
        if thread:
            thread.status = "resolved"

    # ── Log telemetry ────────────────────────────────────────────────
    log = GenerationLog(
        project_id=project_id,
        job_id=job_id,
        chapter_number=chapter_number,
        stage="5",
        model="flash",
        latency_ms=latency_ms,
        maturity_level=maturity_level,
    )
    db.add(log)
    await db.flush()

    logger.info(
        "Stage 5 complete | project=%s chapter=%d | "
        "bible_additions=%d | threads_opened=%d | resolutions=%d",
        project_id,
        chapter_number,
        len(delta.get("bible_additions", [])),
        len(delta.get("plot_threads_opened", [])),
        sum(len(v) for v in cleaned_resolutions.values()),
    )

    return delta
