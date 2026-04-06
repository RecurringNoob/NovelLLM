"""
app/schemas/common.py — Shared Pydantic types used across all schemas.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    """Generic wrapping envelope for list endpoints."""
    data: T
    total: int | None = None


class NotImplementedResponse(BaseModel):
    """Placeholder response for stubbed endpoints (Phase 1)."""
    status: str = "not_implemented"
    phase: int = 1
    message: str = "This endpoint will be implemented in a future phase."


class HealthResponse(BaseModel):
    status: str
    db: str
    redis: str
    environment: str


class PaginationParams(BaseModel):
    limit: int = 20
    offset: int = 0


# ── Base config for all ORM-linked schemas ────────────────────────
class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)
