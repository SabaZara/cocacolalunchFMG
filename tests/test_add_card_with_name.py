"""Adding ONE person from the admin page: card id + typed name, no CSV.

The roster import only accepts Coca-Cola DDD-DDDDD codes, so adding a single
person used to mean hand-building a spreadsheet. The add-card box now takes an
optional name, which lands on people.full_name and is picked up everywhere the
roster has no entry for that card.
"""
from __future__ import annotations

CARD = "3375795142"          # POS id -> 054-35782
NAME = "შოთა ლომიძე"


def _mk(ctx):
    """Log in (cookie session) and return (client, tunnel headers)."""
    c, H = ctx["client"], ctx["headers"]
    r = c.post("/api/login", headers=H,
               json={"username": ctx["admin_user"], "password": ctx["admin_pass"]})
    assert r.status_code == 200, r.text
    return c, H


def test_create_with_name_is_stored_and_listed(app_ctx):
    c, H = _mk(app_ctx)
    r = c.post("/api/people", headers=H,
               json={"card_id": CARD, "full_name": NAME})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["card_id"] == CARD
    assert body["full_name"] == NAME
    # Derived, never typed by the operator.
    assert body["cc_code"] == "054-35782"
    # No roster entry exists, so the name is the typed one.
    assert body["from_roster"] is False

    listed = {p["card_id"]: p for p in c.get("/api/people", headers=H).json()}
    assert listed[CARD]["full_name"] == NAME


def test_name_is_optional(app_ctx):
    c, H = _mk(app_ctx)
    r = c.post("/api/people", headers=H, json={"card_id": "9001"})
    assert r.status_code == 201, r.text
    # Placeholder is not shown as a real name.
    assert r.json()["full_name"] in ("", "----")


def test_typed_name_reaches_receipt_and_report(app_ctx):
    c, H = _mk(app_ctx)
    c.post("/api/people", headers=H,
           json={"card_id": CARD, "full_name": NAME})

    # A real tap at the kiosk.
    r = c.post("/api/scan", json={"card_id": CARD})
    assert r.status_code == 200, r.text

    from sqlmodel import Session, select
    from app.models import ReceiptJob
    from app.reports import detail_rows
    import app.db as db
    from datetime import date

    with Session(db.engine) as s:
        # The receipt body is snapshotted when the tap is flushed.
        job = s.exec(select(ReceiptJob)).first()
        if job is not None:            # receipts disabled in this env -> skip
            assert NAME in job.body
            assert "არაიდენტიფიცირებული" not in job.body

        today = date.today()
        rows = detail_rows(s, today, today)
        assert rows, "no detail rows for today"
        assert any(row.get("full_name") == NAME for row in rows), rows


def test_roster_wins_over_typed_name(app_ctx):
    """If Coca-Cola's list also has the card, their spelling is authoritative."""
    c, H = _mk(app_ctx)
    c.post("/api/people", headers=H,
           json={"card_id": CARD, "full_name": "ხელით ნაწერი"})

    csv = "CardNo,FirstName,LastName\n054-35782,შოთა,ლომიძე\n".encode("utf-8")
    r = c.post("/api/people/roster-import", headers=H,
               files={"file": ("roster.csv", csv, "text/csv")})
    assert r.status_code == 200, r.text
    assert r.json()["added"] == 1

    listed = {p["card_id"]: p for p in c.get("/api/people", headers=H).json()}
    assert listed[CARD]["full_name"] == NAME
    assert listed[CARD]["from_roster"] is True
