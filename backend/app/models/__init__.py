"""
app/models/__init__.py — Re-exports all ORM models so Alembic autodiscovers them.
Import order matters: base tables before tables with FK dependencies.
"""
from app.models.project import Project, Series  # noqa: F401
from app.models.character import Character, CharacterPresence  # noqa: F401
from app.models.world import Location, PlotThread, OutlineChapter, TimelineCell  # noqa: F401
from app.models.chapter import (  # noqa: F401
    Chapter,
    ChapterStateSnapshot,
    ChapterDependency,
    ProseCheckpoint,
)
from app.models.bible import (  # noqa: F401
    BibleEvent,
    PendingBibleUpdate,
    GenerationLog,
    PromptTemplate,
    PromptTemplateActivation,
)
from app.models.job import GenerationJob  # noqa: F401  ← Phase 2
from app.models.dialogue import DialogueSession  # noqa: F401
from app.models.style import StyleProfile  # noqa: F401
from app.models.analytics import ChapterAnalytics  # noqa: F401
from app.models.eval import EvalExperiment, EvalResult  # noqa: F401

__all__ = [
    "Project",
    "Series",
    "Character",
    "CharacterPresence",
    "Location",
    "PlotThread",
    "OutlineChapter",
    "TimelineCell",
    "Chapter",
    "ChapterStateSnapshot",
    "ChapterDependency",
    "ProseCheckpoint",
    "BibleEvent",
    "PendingBibleUpdate",
    "GenerationLog",
    "PromptTemplate",
    "PromptTemplateActivation",
    "GenerationJob",
    "DialogueSession",
    "StyleProfile",
    "ChapterAnalytics",
    "EvalExperiment",
    "EvalResult",
]
