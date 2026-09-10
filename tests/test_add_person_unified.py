"""One add box that accepts EITHER a POS card id or a Coca-Cola code.

POS -> CC is one-way (256 POS ids per code), so the two identifiers cannot
produce the same thing:
  * POS id  -> a card row the kiosk matches on immediately.
  * CC code -> a roster NAME only; the card attaches itself on its first tap.
"""
from __future__ import annotations

POS = "3375795142"
CC = "054-35782"
NAME = "შოთა ლომიძე"


def _login(ctx):
    c, H = ctx["client"], ctx["headers"]
    r = c.post("/api/login", headers=H,
               json={"username": ctx["admin_user"], "password": ctx["admin_pass"]})
    assert r.status_code == 200, r.text
    return c, H


def test_pos_id_creates_card(app_ctx):
    c, H = _login(app_ctx)
    r = c.post("/api/people/add", headers=H,
               json={"identifier": POS, "full_name": NAME})
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["kind"] == "card"
    assert j["card_id"] == POS
    assert j["cc_code"] == CC          # derived, never typed
    listed = {p["card_id"]: p for p in c.get("/api/people", headers=H).json()}
    assert listed[POS]["full_name"] == NAME


def test_cc_code_creates_roster_name_not_a_card(app_ctx):
    c, H = _login(app_ctx)
    r = c.post("/api/people/add", headers=H,
               json={"identifier": CC, "full_name": NAME})
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["kind"] == "roster"
    assert j["cc_code"] == CC
    # No phantom card row was invented from a code that cannot yield one.
    assert c.get("/api/people", headers=H).json() == []
    assert c.get("/api/people/roster-status", headers=H).json()["count"] == 1


def test_cc_name_attaches_when_the_card_first_taps(app_ctx):
    """The point of the roster path: add the name now, card works later."""
    c, H = _login(app_ctx)
    c.post("/api/people/add", headers=H, json={"identifier": CC, "full_name": NAME})

    # The physical card taps for the first time -> auto-registers.
    assert c.post("/api/scan", json={"card_id": POS}).status_code == 200

    listed = {p["card_id"]: p for p in c.get("/api/people", headers=H).json()}
    assert listed[POS]["full_name"] == NAME
    assert listed[POS]["from_roster"] is True


def test_sloppy_cc_code_is_accepted(app_ctx):
    """Excel eats leading zeros: '54-35782' still means 054-35782."""
    c, H = _login(app_ctx)
    r = c.post("/api/people/add", headers=H,
               json={"identifier": "54-35782", "full_name": NAME})
    assert r.status_code == 201, r.text
    assert r.json()["cc_code"] == CC


def test_cc_code_without_a_name_is_rejected(app_ctx):
    """A code alone carries no information: no card, no name. Refuse it."""
    c, H = _login(app_ctx)
    r = c.post("/api/people/add", headers=H, json={"identifier": CC})
    assert r.status_code == 422, r.text


def test_pos_id_without_a_name_is_fine(app_ctx):
    c, H = _login(app_ctx)
    r = c.post("/api/people/add", headers=H, json={"identifier": "9001"})
    assert r.status_code == 201, r.text
    assert r.json()["kind"] == "card"


def test_duplicate_card_is_reported(app_ctx):
    c, H = _login(app_ctx)
    c.post("/api/people/add", headers=H, json={"identifier": POS})
    r = c.post("/api/people/add", headers=H, json={"identifier": POS})
    assert r.status_code == 409, r.text


def test_readding_same_cc_code_updates_the_name(app_ctx):
    c, H = _login(app_ctx)
    c.post("/api/people/add", headers=H, json={"identifier": CC, "full_name": "ძველი სახელი"})
    r = c.post("/api/people/add", headers=H, json={"identifier": CC, "full_name": NAME})
    assert r.status_code == 201, r.text
    assert r.json()["created"] is False        # updated, not duplicated
    assert c.get("/api/people/roster-status", headers=H).json()["count"] == 1
