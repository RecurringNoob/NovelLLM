"""
app/core/exceptions.py — Custom exception classes.
"""
from __future__ import annotations


class NoteLMBaseError(Exception):
    """Base exception for all application errors."""
    pass


# ── Pipeline Exceptions ───────────────────────────────────────────
class SafetyBlockError(NoteLMBaseError):
    """Raised when Gemini blocks output due to safety settings."""

    def __init__(self, checkpoint_num: int = 0, words_written: int = 0):
        self.checkpoint_num = checkpoint_num
        self.words_written = words_written
        super().__init__(f"Safety block at checkpoint {checkpoint_num}")


class InjectionDetectedError(NoteLMBaseError):
    """Raised when prompt injection is detected (regex or Gemini eval)."""

    def __init__(self, layer: str, reason: str):
        self.layer = layer   # "regex" | "gemini_eval"
        self.reason = reason
        super().__init__(f"Injection detected [{layer}]: {reason}")


class BudgetExceededError(NoteLMBaseError):
    """Raised when a project's hard cost limit is exceeded."""

    def __init__(self, spent_cents: int, budget_cents: int, project_id: str):
        self.spent_cents = spent_cents
        self.budget_cents = budget_cents
        self.project_id = project_id
        super().__init__(
            f"Budget exceeded for project {project_id}: "
            f"{spent_cents}¢ spent of {budget_cents}¢"
        )


# ── Data Integrity Exceptions ─────────────────────────────────────
class VersionConflictError(NoteLMBaseError):
    """
    Raised during OCC (Optimistic Concurrency Control) when the entity
    was modified between when the AI saw it and when the user accepts.
    """

    def __init__(
        self,
        entity_id: str,
        ai_saw_version: int,
        current_version: int,
        ai_changes: dict,
    ):
        self.entity_id = entity_id
        self.ai_saw_version = ai_saw_version
        self.current_version = current_version
        self.ai_changes = ai_changes
        super().__init__(
            f"Version conflict on entity {entity_id}: "
            f"AI saw v{ai_saw_version}, current is v{current_version}"
        )


class EntityNotFoundError(NoteLMBaseError):
    """Raised when a requested entity does not exist in the DB."""

    def __init__(self, entity_type: str, entity_id: str):
        self.entity_type = entity_type
        self.entity_id = entity_id
        super().__init__(f"{entity_type} '{entity_id}' not found")


# ── NER Guard ─────────────────────────────────────────────────────
class NERGuardTriggeredError(NoteLMBaseError):
    """Raised when Stage 4 spaCy guard detects new named entities not in Stage 3."""

    def __init__(self, new_entities: list[str]):
        self.new_entities = new_entities
        super().__init__(f"NER guard triggered: new entities {new_entities}")


# ── Pipeline stage errors ─────────────────────────────────────────
class StageTimeoutError(NoteLMBaseError):
    """Raised when a pipeline stage exceeds its timeout threshold."""

    def __init__(self, stage: str, timeout_seconds: int):
        self.stage = stage
        self.timeout_seconds = timeout_seconds
        super().__init__(f"Stage {stage} timed out after {timeout_seconds}s")


class InvalidStageOutputError(NoteLMBaseError):
    """Raised when a stage produces output that fails schema validation."""

    def __init__(self, stage: str, detail: str):
        self.stage = stage
        super().__init__(f"Invalid output from stage {stage}: {detail}")
