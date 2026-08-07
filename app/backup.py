"""Database backup: local timestamped copies + upload to a PRIVATE GitHub repo.

Local backups are consistent copies of the SQLite file (online backup API)
written to a `backups/` folder next to the DB — pure local disk, no internet.

GitHub upload sends a fresh snapshot to a PRIVATE repo via the Contents API.
The repo + token are stored on the kiosk in `.backup-config.json` (gitignored,
never in the public code repo) and are set ONCE through the admin page over the
tunnel. Status never returns the token.

Monthly automation (best-effort, on app startup):
  * local auto-backup if the newest local backup is older than ~30 days;
  * GitHub auto-upload if configured and the last upload is older than ~30 days.
"""
from __future__ import annotations

import base64
import json
import sqlite3
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import ROOT, get_settings

GH_CONFIG_PATH = ROOT / ".backup-config.json"


def _backups_dir() -> Path:
    d = get_settings().db_path.parent / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


@dataclass
class BackupInfo:
    name: str
    size: int
    created: str

    def as_dict(self) -> dict:
        return {"name": self.name, "size": self.size, "created": self.created}


def create_backup(reason: str = "manual") -> Path:
    """Write a consistent copy of the DB to backups/. Returns the new path."""
    settings = get_settings()
    dest = _backups_dir() / f"lunch-{_timestamp()}-{reason}.db"
    src_conn = sqlite3.connect(str(settings.db_path))
    try:
        dst_conn = sqlite3.connect(str(dest))
        try:
            src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
    finally:
        src_conn.close()
    return dest


def list_backups() -> list[BackupInfo]:
    out: list[BackupInfo] = []
    for p in sorted(_backups_dir().glob("lunch-*.db"), reverse=True):
        st = p.stat()
        created = datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(timespec="seconds")
        out.append(BackupInfo(name=p.name, size=st.st_size, created=created))
    return out


def latest_backup() -> BackupInfo | None:
    backups = list_backups()
    return backups[0] if backups else None


def _parse_ts_from_name(name: str) -> datetime | None:
    try:
        parts = name.split("-")
        return datetime.strptime(parts[1] + parts[2], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    except (IndexError, ValueError):
        return None


# How many backups to keep. GitHub stays lean (rolling weekly); local can hold
# more since disk is cheap. Weekly cadence for the auto jobs.
GH_KEEP = 4
LOCAL_KEEP = 30
WEEKLY_DAYS = 7


def prune_local(keep: int = LOCAL_KEEP) -> int:
    """Delete oldest local backups beyond `keep`. Returns number removed."""
    files = sorted(_backups_dir().glob("lunch-*.db"), reverse=True)  # newest first
    removed = 0
    for p in files[keep:]:
        try:
            p.unlink()
            removed += 1
        except OSError:
            pass
    return removed


def auto_backup_if_due(period_days: int = WEEKLY_DAYS) -> Path | None:
    """Weekly local backup if the newest is older than period; prune old ones."""
    latest = latest_backup()
    due = True
    if latest is not None:
        ts = _parse_ts_from_name(latest.name)
        if ts is not None and (datetime.now(timezone.utc) - ts).days < period_days:
            due = False
    made = create_backup(reason="auto") if due else None
    prune_local()
    return made


def backup_path(name: str) -> Path | None:
    """Resolve a backup file by name, guarding against path traversal."""
    if "/" in name or "\\" in name or ".." in name:
        return None
    p = _backups_dir() / name
    return p if p.exists() and p.is_file() else None


# ----------------------------- GitHub upload -------------------------------- #
def load_gh_config() -> dict:
    cfg = {"repo": "", "token": "", "last_upload": None, "last_result": None}
    try:
        cfg.update(json.loads(GH_CONFIG_PATH.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    return cfg


def save_gh_config(repo: str | None = None, token: str | None = None, **extra) -> dict:
    """Merge-and-save. The token is only replaced when a non-empty one is given."""
    cfg = load_gh_config()
    if repo is not None:
        cfg["repo"] = repo.strip().removeprefix("https://github.com/").strip("/")
    if token:  # empty string keeps the existing token
        cfg["token"] = token.strip()
    cfg.update(extra)
    GH_CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=1),
                              encoding="utf-8")
    return cfg


def gh_status() -> dict:
    """Config state for the admin UI — NEVER includes the token itself."""
    cfg = load_gh_config()
    return {
        "repo": cfg.get("repo", ""),
        "token_set": bool(cfg.get("token")),
        "configured": bool(cfg.get("repo") and cfg.get("token")),
        "last_upload": cfg.get("last_upload"),
        "last_result": cfg.get("last_result"),
    }


def _ssl_contexts() -> list[ssl.SSLContext | None]:
    contexts: list[ssl.SSLContext | None] = []
    try:
        import certifi
        contexts.append(ssl.create_default_context(cafile=certifi.where()))
    except Exception:  # noqa: BLE001
        pass
    contexts.append(None)
    unver = ssl.create_default_context()
    unver.check_hostname = False
    unver.verify_mode = ssl.CERT_NONE
    contexts.append(unver)
    return contexts


def _gh_request(url: str, token: str, method: str = "GET",
                payload: dict | None = None) -> tuple[int, str]:
    """Call the GitHub API (GET/PUT/DELETE), robust to Windows SSL issues."""
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    last_exc: Exception | None = None
    for ctx in _ssl_contexts():
        try:
            req = urllib.request.Request(
                url, data=data, method=method,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "lunch-kiosk-backup",
                    "Content-Type": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=120, context=ctx) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8", "replace")
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
    raise RuntimeError(f"GitHub API unreachable: {last_exc}")


# Backwards-compatible alias used by tests that patch the network layer.
def _gh_put(url: str, payload: dict, token: str) -> tuple[int, str]:
    return _gh_request(url, token, "PUT", payload)


def _gh_list(repo: str, token: str) -> list[dict]:
    """List files under backups/ in the repo (name + sha). [] if none/404."""
    url = f"https://api.github.com/repos/{repo}/contents/backups"
    status, body = _gh_request(url, token, "GET")
    if status != 200:
        return []
    try:
        items = json.loads(body)
    except ValueError:
        return []
    return [{"name": i["name"], "sha": i["sha"]}
            for i in items if i.get("type") == "file"
            and i["name"].startswith("lunch-") and i["name"].endswith(".db")]


def _gh_delete(repo: str, name: str, sha: str, token: str) -> None:
    url = f"https://api.github.com/repos/{repo}/contents/backups/{name}"
    _gh_request(url, token, "DELETE",
                {"message": f"prune old backup {name}", "sha": sha})


def _gh_error(status: int, body: str) -> str:
    detail = ""
    try:
        detail = json.loads(body).get("message", "")
    except ValueError:
        pass
    return f"HTTP {status} {detail}".strip()


def upload_to_github() -> dict:
    """Snapshot the DB and upload it to the private repo as ONE file per day
    (lunch-YYYYMMDD.db, overwritten if run twice in a day), then keep only the
    GH_KEEP newest backups in the repo so it never grows large.
    """
    cfg = load_gh_config()
    repo, token = cfg.get("repo", ""), cfg.get("token", "")
    if not repo or not token:
        return {"ok": False, "error": "GitHub რეპო/ტოკენი არ არის მითითებული."}

    path = create_backup(reason="github")
    day_name = f"lunch-{datetime.now(timezone.utc).strftime('%Y%m%d')}.db"
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    url = f"https://api.github.com/repos/{repo}/contents/backups/{day_name}"
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")

    try:
        existing = _gh_list(repo, token)
        # overwrite today's file if it already exists (Contents API needs the sha)
        sha = next((e["sha"] for e in existing if e["name"] == day_name), None)
        payload = {"message": f"kiosk backup {day_name}", "content": b64}
        if sha:
            payload["sha"] = sha
        status, body = _gh_request(url, token, "PUT", payload)
    except RuntimeError as exc:
        save_gh_config(last_result=f"error: {exc}")
        return {"ok": False, "error": str(exc)}

    if status not in (200, 201):
        err = _gh_error(status, body)
        save_gh_config(last_result=f"error: {err}")
        return {"ok": False, "error": err}

    # prune the repo down to the GH_KEEP newest (names sort lexicographically).
    # GitHub's Contents API is eventually consistent, so the re-list may not yet
    # include the file we just PUT — union it in and never delete it here.
    pruned = 0
    try:
        listed = {e["name"]: e["sha"] for e in _gh_list(repo, token)}
        listed.setdefault(day_name, None)  # ensure today's file is counted/kept
        names = sorted(listed, reverse=True)  # newest first
        for name in names[GH_KEEP:]:
            if name == day_name:
                continue  # never prune the file we just uploaded
            sha = listed.get(name)
            if sha:
                _gh_delete(repo, name, sha, token)
                pruned += 1
    except Exception:  # noqa: BLE001
        pass  # pruning is best-effort; the upload already succeeded

    save_gh_config(last_upload=now_iso, last_result="ok")
    return {"ok": True, "name": day_name, "size": path.stat().st_size,
            "pruned": pruned}


def auto_github_upload_if_due(period_days: int = WEEKLY_DAYS) -> None:
    """Best-effort weekly upload — silently skips when offline/unconfigured."""
    st = gh_status()
    if not st["configured"]:
        return
    last = st.get("last_upload")
    if last:
        try:
            dt = datetime.fromisoformat(last)
            if (datetime.now(timezone.utc) - dt).days < period_days:
                return
        except ValueError:
            pass
    try:
        upload_to_github()
    except Exception:  # noqa: BLE001
        pass
