"""Runtime settings API (admin-editable). Gated (login + tunnel secret).

Currently: the meal day-split time used by the quantitative report.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import app_config as AC
from ..security import get_current_admin

router = APIRouter(prefix="/api/settings", tags=["settings"],
                   dependencies=[Depends(get_current_admin)])


class MealSplit(BaseModel):
    meal_split: str


@router.get("")
def get_settings() -> dict:
    return AC.get_settings_public()


@router.post("")
def update_settings(payload: MealSplit) -> dict:
    try:
        AC.set_meal_split(payload.meal_split)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return AC.get_settings_public()
