"""Backup API: local snapshots, download, and GitHub private-repo upload.

Gated (admin login + tunnel secret). The GitHub token is written via
/github-config and stored only on the kiosk; status never returns it.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .. import backup as B
from ..security import get_current_admin

router = APIRouter(prefix="/api/backup", tags=["backup"],
                   dependencies=[Depends(get_current_admin)])


@router.get("/status")
def status() -> dict:
    latest = B.latest_backup()
    return {
        "latest": latest.as_dict() if latest else None,
        "count": len(B.list_backups()),
        "github": B.gh_status(),
    }


@router.get("/list")
def list_all() -> dict:
    return {"backups": [b.as_dict() for b in B.list_backups()]}


@router.post("/now")
def backup_now() -> dict:
    path = B.create_backup(reason="manual")
    return {"ok": True, "name": path.name}


@router.get("/download")
def download_current() -> FileResponse:
    """Download a fresh, consistent copy of the live database."""
    path = B.create_backup(reason="download")
    return FileResponse(path, media_type="application/octet-stream",
                        filename=path.name)


@router.get("/download/{name}")
def download_named(name: str) -> FileResponse:
    path = B.backup_path(name)
    if path is None:
        raise HTTPException(status_code=404, detail="ბექაფი ვერ მოიძებნა.")
    return FileResponse(path, media_type="application/octet-stream",
                        filename=path.name)


class GhConfig(BaseModel):
    repo: str
    token: str | None = None  # empty/omitted keeps the stored token


@router.post("/github-config")
def github_config(payload: GhConfig) -> dict:
    if not payload.repo.strip():
        raise HTTPException(status_code=422, detail="მიუთითეთ რეპო (owner/repo).")
    B.save_gh_config(repo=payload.repo, token=payload.token or None)
    return {"ok": True, "github": B.gh_status()}


@router.post("/github-upload")
def github_upload() -> dict:
    result = B.upload_to_github()
    result["github"] = B.gh_status()
    return result
