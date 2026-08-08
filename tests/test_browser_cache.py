"""Browser cache housekeeping.

The kiosk page is served `no-store`, so staleness is handled — but the on-disk
cache still grows for months on a machine nobody looks at, and a full disk
stops SQLite writing, i.e. scans fail at the reader. A corrupted cache has also
broken the scan page on this kiosk before.

The risk in cleaning it is doing harm: deleting a live cache corrupts the
profile, and deleting the wrong folder loses the operator's logins.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import scripts.clear_browser_cache as cbc  # noqa: E402


def _fake_profile(tmp_path: Path) -> tuple[Path, Path]:
    """A browser User Data dir with caches and personal data."""
    user_data = tmp_path / "User Data"
    profile = user_data / "Default"
    (profile / "Cache").mkdir(parents=True)
    (profile / "Code Cache").mkdir(parents=True)
    (profile / "GPUCache").mkdir(parents=True)
    (profile / "Service Worker" / "CacheStorage").mkdir(parents=True)
    (profile / "Cache" / "blob.bin").write_bytes(b"x" * 2_000_000)
    # Personal data that must NEVER be touched.
    (profile / "History").write_text("history")
    (profile / "Bookmarks").write_text("bookmarks")
    (profile / "Cookies").write_text("cookies")
    (profile / "Login Data").write_text("passwords")
    (profile / "Preferences").write_text("{}")
    return user_data, profile


def test_skips_a_running_browser(tmp_path, monkeypatch):
    """Deleting a live cache is how profiles get corrupted — never do it."""
    user_data, profile = _fake_profile(tmp_path)
    monkeypatch.setattr(cbc, "_browser_roots", lambda: [("chrome.exe", user_data)])
    monkeypatch.setattr(cbc, "_is_running", lambda p: True)

    freed = cbc.clear_caches()

    assert freed == 0
    assert (profile / "Cache").exists(), "cleared the cache of a running browser"


def test_clears_cache_when_browser_is_closed(tmp_path, monkeypatch):
    user_data, profile = _fake_profile(tmp_path)
    monkeypatch.setattr(cbc, "_browser_roots", lambda: [("chrome.exe", user_data)])
    monkeypatch.setattr(cbc, "_is_running", lambda p: False)

    freed = cbc.clear_caches()

    assert freed > 1                      # the 2 MB blob was reclaimed
    assert not (profile / "Cache").exists()
    assert not (profile / "Code Cache").exists()
    assert not (profile / "GPUCache").exists()
    assert not (profile / "Service Worker" / "CacheStorage").exists()


def test_never_deletes_personal_data(tmp_path, monkeypatch):
    """History, bookmarks, cookies and saved logins must all survive."""
    user_data, profile = _fake_profile(tmp_path)
    monkeypatch.setattr(cbc, "_browser_roots", lambda: [("chrome.exe", user_data)])
    monkeypatch.setattr(cbc, "_is_running", lambda p: False)

    cbc.clear_caches()

    for name in ("History", "Bookmarks", "Cookies", "Login Data", "Preferences"):
        assert (profile / name).exists(), f"{name} was deleted"


def test_unknown_process_state_is_treated_as_running(monkeypatch):
    """If we cannot tell whether the browser is up, do nothing (fail safe)."""
    def boom(*a, **k):
        raise OSError("tasklist unavailable")

    monkeypatch.setattr(cbc.subprocess, "run", boom)
    assert cbc._is_running("chrome.exe") is True


def test_main_never_raises(tmp_path, monkeypatch):
    """Housekeeping must never stop the kiosk from starting."""
    def boom():
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(cbc, "clear_caches", lambda verbose=False: boom())
    assert cbc.main([]) == 0


def test_missing_browser_dirs_are_harmless(tmp_path, monkeypatch):
    monkeypatch.setattr(cbc, "_browser_roots", lambda: [])
    assert cbc.clear_caches() == 0
