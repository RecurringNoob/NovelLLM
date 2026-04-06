"""
app/dependencies.py — Shared FastAPI dependency providers.

Phase 1: get_current_user returns a hardcoded dev user UUID.
Phase 9: Replace with real JWT extraction + DB lookup.
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db


# ── Database session ──────────────────────────────────────────────
DbDep = Annotated[AsyncSession, Depends(get_db)]


# ── Current user (Phase 1 stub) ───────────────────────────────────
class DevUser:
    """Placeholder user for Phase 1. Replaced by real JWT auth in Phase 9."""

    def __init__(self, user_id: str = settings.dev_user_id):
        self.id = uuid.UUID(user_id)
        self.email = "dev@notelm.local"
        self.is_admin = True


async def get_current_user() -> DevUser:
    """
    Phase 1 stub — always returns the dev user.
    Phase 9 will decode a Bearer JWT, validate it, and fetch from DB.
    """
    return DevUser()


CurrentUser = Annotated[DevUser, Depends(get_current_user)]
