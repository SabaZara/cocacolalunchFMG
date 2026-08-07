"""Scan API — ALWAYS available locally (offline kiosk). Never gated."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session

from ..db import get_session
from ..scan_service import ScanResult, decide_scan

router = APIRouter(prefix="/api", tags=["scan"])


class ScanRequest(BaseModel):
    card_id: str


class ScanResponse(BaseModel):
    status: str
    reason: str | None = None
    scanned_at: str | None = None
    remaining: int | None = None
    limit: int | None = None


@router.post("/scan", response_model=ScanResponse)
def scan(payload: ScanRequest, session: Session = Depends(get_session)) -> ScanResult:
    return decide_scan(session, payload.card_id)
