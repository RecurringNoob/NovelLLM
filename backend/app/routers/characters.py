"""
app/routers/characters.py — Character CRUD + AI deepening stub.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.dependencies import DbDep, CurrentUser
from app.models.character import Character
from app.schemas.character import CharacterCreate, CharacterRead, CharacterUpdate, CharacterDeepenRequest
from app.schemas.common import NotImplementedResponse

router = APIRouter(prefix="/projects/{project_id}/characters", tags=["characters"])


@router.get("", response_model=list[CharacterRead])
async def list_characters(project_id: uuid.UUID, db: DbDep, user: CurrentUser):
    result = await db.execute(
        select(Character).where(Character.project_id == project_id).order_by(Character.name)
    )
    return result.scalars().all()


@router.post("", response_model=CharacterRead, status_code=status.HTTP_201_CREATED)
async def create_character(project_id: uuid.UUID, body: CharacterCreate, db: DbDep, user: CurrentUser):
    character = Character(
        project_id=project_id,
        name=body.name,
        bio=body.bio,
        data=body.data,
    )
    db.add(character)
    await db.flush()
    await db.refresh(character)
    return character


@router.get("/{character_id}", response_model=CharacterRead)
async def get_character(project_id: uuid.UUID, character_id: uuid.UUID, db: DbDep, user: CurrentUser):
    char = await db.get(Character, character_id)
    if not char or char.project_id != project_id:
        raise HTTPException(status_code=404, detail="Character not found")
    return char


@router.patch("/{character_id}", response_model=CharacterRead)
async def update_character(project_id: uuid.UUID, character_id: uuid.UUID, body: CharacterUpdate, db: DbDep, user: CurrentUser):
    char = await db.get(Character, character_id)
    if not char or char.project_id != project_id:
        raise HTTPException(status_code=404, detail="Character not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(char, k, v)
    char.version += 1
    await db.flush()
    await db.refresh(char)
    return char


@router.delete("/{character_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_character(project_id: uuid.UUID, character_id: uuid.UUID, db: DbDep, user: CurrentUser):
    char = await db.get(Character, character_id)
    if not char or char.project_id != project_id:
        raise HTTPException(status_code=404, detail="Character not found")
    await db.delete(char)


@router.post("/{character_id}/deepen", response_model=NotImplementedResponse)
async def deepen_character(project_id: uuid.UUID, character_id: uuid.UUID, body: CharacterDeepenRequest, db: DbDep, user: CurrentUser):
    """AI-powered backstory deepening (Phase 7)."""
    return NotImplementedResponse()
