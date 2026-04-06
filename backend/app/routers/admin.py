"""
app/routers/admin.py — Admin dashboard, prompt rollback, and eval suite endpoints.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.dependencies import DbDep, CurrentUser
from app.schemas.bible import PromptRollbackRequest
from app.schemas.common import NotImplementedResponse

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/dashboard", response_model=NotImplementedResponse)
async def admin_dashboard(db: DbDep, user: CurrentUser):
    """
    Observability + A/B testing dashboard data (Phase 9).
    Returns: queue depth, failure rate, safety block rate, NER guard rate,
             active experiments, recent eval results.
    """
    return NotImplementedResponse()


@router.post("/prompts/rollback/{stage}", response_model=NotImplementedResponse)
async def rollback_prompt_template(stage: str, body: PromptRollbackRequest, db: DbDep, user: CurrentUser):
    """
    Rollback a prompt template to a specific version (Phase 9, Section 35).
    Invalidates all related stage caches.
    """
    return NotImplementedResponse()


@router.get("/eval/run", response_model=NotImplementedResponse)
async def run_eval_suite(db: DbDep, user: CurrentUser):
    """
    Trigger the LLM-as-Judge prompt evaluation suite (Phase 9, Section 29).
    CI gate: fail if overall_score < 0.75.
    """
    return NotImplementedResponse()
