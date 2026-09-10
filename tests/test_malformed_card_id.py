"""A stuck reader must not be able to poison the card list.

Production incident: a reader emitted "3377429046" followed by ~4500 repeated
digits. It registered as a card. The string had nothing to wrap on, so its
table cell stretched to ~45000px and shoved every other column off-screen —
the admin page looked like it had lost its name/code/status columns entirely.

Two independent defences, tested here:
  1. the scan path refuses an id that long (it can't be a real card);
  2. even if such a row exists, the id column is width-capped and breakable.
"""
from __future__ import annotations

import re
from pathlib import Path

from app.scan_service import MAX_CARD_ID_LEN, normalize_card_id

ROOT = Path(__file__).resolve().parent.parent
STUCK = "3377429046" + "6" * 4546          # the real one, 4556 chars


def test_real_incident_id_is_rejected():
    assert len(STUCK) == 4556
    assert normalize_card_id(STUCK) == ""


def test_real_card_ids_still_pass_untouched():
    for good in ("3375795142", "00390", "0067305985", "0134052039"):
        assert normalize_card_id(good) == good      # leading zeros preserved


def test_whitespace_still_trimmed():
    assert normalize_card_id("  00390 \n") == "00390"


def test_boundary_of_the_length_guard():
    assert normalize_card_id("9" * MAX_CARD_ID_LEN) == "9" * MAX_CARD_ID_LEN
    assert normalize_card_id("9" * (MAX_CARD_ID_LEN + 1)) == ""


def test_stuck_reader_is_denied_and_creates_no_card(app_ctx):
    """End to end: the tap is refused and leaves no row behind."""
    c, H = app_ctx["client"], app_ctx["headers"]
    r = c.post("/api/login", headers=H,
               json={"username": app_ctx["admin_user"], "password": app_ctx["admin_pass"]})
    assert r.status_code == 200

    res = c.post("/api/scan", json={"card_id": STUCK})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "DENIED"
    assert body["reason"] == "ბარათი ვერ წაიკითხა"

    # The whole point: no junk row is left in the card list.
    assert c.get("/api/people", headers=H).json() == []


def test_id_column_is_width_capped_in_css():
    """The layout must survive a long id even if one reaches the table."""
    css = (ROOT / "static" / "app.css").read_text(encoding="utf-8")
    block = re.search(r"td\.ltr\.mono\s*\{([^}]*)\}", css)
    assert block, "id-column guard missing from app.css"
    rules = block.group(1)
    assert "max-width" in rules
    assert "anywhere" in rules or "break-all" in rules
