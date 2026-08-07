"""Runtime settings API (admin-editable). Gated (login + tunnel secret).

  * meal_split  — the day-split time used by the quantitative report.
  * daily_limit — meals per card per day, ONE number for every card.

Both fields are optional in the POST body, so the admin page can save either
one on its own without clobbering the other.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import app_config as AC
from ..security import get_current_admin

router = APIRouter(prefix="/api/settings", tags=["settings"],
                   dependencies=[Depends(get_current_admin)])


class SettingsUpdate(BaseModel):
    meal_split: str | None = None
    daily_limit: int | None = None


@router.get("")
def get_settings() -> dict:
    return AC.get_settings_public()


@router.post("")
def update_settings(payload: SettingsUpdate) -> dict:
    try:
        if payload.meal_split is not None:
            AC.set_meal_split(payload.meal_split)
        if payload.daily_limit is not None:
            AC.set_daily_limit(payload.daily_limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return AC.get_settings_public()
