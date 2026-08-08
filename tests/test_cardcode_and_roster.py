"""POS <-> Coca-Cola card code conversion, and the personnel roster.

The kiosk reader returns a 32-bit POS id; Coca-Cola's own systems know people
by the low 24 bits of that number formatted DDD-DDDDD. Everything that puts a
NAME on a report depends on that conversion being exactly right, so the
verified real-world pairs are pinned here.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest
from openpyxl import Workbook
from sqlmodel import Session

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.cardcode import is_cc_code, normalize_cc_code, pos_to_cc  # noqa: E402

# Confirmed against Coca-Cola's own card list.
KNOWN_PAIRS = [
    ("3377269862", "077-03174"),
    ("3378757254", "099-48774"),
    ("3673926606", "251-43982"),
    ("4153314197", "142-35733"),
]


@pytest.mark.parametrize("pos_id,cc", KNOWN_PAIRS)
def test_pos_to_cc_matches_verified_examples(pos_id, cc):
    assert pos_to_cc(pos_id) == cc


def test_pos_to_cc_discards_the_high_byte():
    """Only the low 24 bits survive — that is what makes it many-to-one.

    256 different POS ids share one Coca-Cola code, which is exactly why the
    reverse conversion is not implemented.
    """
    base = 0x00FFFFFF & 3377269862
    codes = {pos_to_cc(str(base + (prefix << 24))) for prefix in range(256)}
    assert len(codes) == 1, "high byte must not affect the code"


def test_pos_to_cc_pads_to_the_fixed_width():
    assert pos_to_cc("1001") == "000-01001"
    assert pos_to_cc("0") == "000-00000"
    assert len(pos_to_cc("255")) == len("000-00255")


def test_pos_to_cc_ignores_non_numeric_ids():
    """A card id need not be numeric; those simply have no Coca-Cola code."""
    for bad in ("", "   ", "ABC123", "12-34", None):
        assert pos_to_cc(bad) == ""


def test_cc_code_validation_and_normalisation():
    assert is_cc_code("077-03174")
    assert not is_cc_code("77-3174")
    # Excel eats leading zeros and adds spaces; both still name the same card.
    assert normalize_cc_code("77-3174") == "077-03174"
    assert normalize_cc_code(" 099 - 48774 ") == "099-48774"
    assert normalize_cc_code("nonsense") == ""


# ------------------------------- roster ------------------------------------ #
def _roster_xlsx(rows: list[tuple[str, str, str]]) -> bytes:
    """Build a sheet shaped like the Coca-Cola export."""
    wb = Workbook()
    ws = wb.active
    ws.append(["CardNo", "User", "FirstName", "LastName"])
    for code, first, last in rows:
        ws.append([code, f"{first} {last}", first, last])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_roster_import_and_name_lookup(app_ctx):
    ctx = app_ctx
    from app import roster

    data = _roster_xlsx([
        ("077-03174", "ია", "ცუცქირიძე"),
        ("142-35733", "უშანგი", "ლაზაშვილი"),
    ])
    with Session(ctx["db"].engine) as s:
        rep = roster.import_roster(s, "cards.xlsx", data)
        assert rep.added == 2 and rep.invalid_count == 0 if hasattr(rep, "invalid_count") \
            else rep.added == 2
        names = roster.names_by_cc_code(s)

    # A scan's POS id resolves to the right person via the conversion.
    assert names[pos_to_cc("3377269862")] == "ია ცუცქირიძე"
    assert names[pos_to_cc("4153314197")] == "უშანგი ლაზაშვილი"


def test_roster_reimport_updates_instead_of_duplicating(app_ctx):
    """Coca-Cola re-export the list; loading it again must not double rows."""
    ctx = app_ctx
    from app import roster

    first = _roster_xlsx([("077-03174", "ია", "ცუცქირიძე")])
    renamed = _roster_xlsx([("077-03174", "ია", "ცუცქირიძე-ახალი")])
    with Session(ctx["db"].engine) as s:
        roster.import_roster(s, "a.xlsx", first)
        rep = roster.import_roster(s, "a.xlsx", renamed)
        assert rep.added == 0 and rep.updated == 1
        names = roster.names_by_cc_code(s)
    assert len(names) == 1
    assert names["077-03174"] == "ია ცუცქირიძე-ახალი"


def test_roster_reports_bad_rows_without_aborting(app_ctx):
    ctx = app_ctx
    from app import roster

    wb = Workbook()
    ws = wb.active
    ws.append(["CardNo", "User", "FirstName", "LastName"])
    ws.append(["077-03174", "ია ცუცქირიძე", "ია", "ცუცქირიძე"])
    ws.append(["NOT-A-CODE", "x", "x", "y"])          # invalid -> reported
    ws.append(["251-43982", "", "", ""])              # no name -> reported
    ws.append(["099-48774", "ნონა გვრიტიშვილი", "ნონა", "გვრიტიშვილი"])
    buf = io.BytesIO()
    wb.save(buf)

    with Session(ctx["db"].engine) as s:
        rep = roster.import_roster(s, "c.xlsx", buf.getvalue())

    d = rep.as_dict()
    assert d["added"] == 2          # the two good rows still landed
    assert d["invalid_count"] == 2
    assert {i["row"] for i in d["invalid"]} == {3, 4}


def test_reports_show_roster_name_over_typed_name(app_ctx):
    """Coca-Cola's spelling wins over a hand-typed one.

    Hand-typing is what produced "ურა ლაბაშვილი" for the person the official
    list calls "უშანგი ლაზაშვილი"; the roster is the authority.
    """
    ctx = app_ctx
    c = ctx["client"]
    H = ctx["headers"]
    c.post("/api/login", headers=H,
           json={"username": ctx["admin_user"], "password": ctx["admin_pass"]})

    c.post("/api/scan", json={"card_id": "4153314197"})
    pid = c.get("/api/people?q=4153314197", headers=H).json()[0]["id"]
    c.put(f"/api/people/{pid}", headers=H, json={"full_name": "ურა ლაბაშვილი"})

    data = _roster_xlsx([("142-35733", "უშანგი", "ლაზაშვილი")])
    c.post("/api/people/roster-import", headers=H,
           files={"file": ("r.xlsx", data, "application/octet-stream")})

    from datetime import date
    d = date.today().isoformat()
    body = c.get(f"/api/reports/export?from={d}&to={d}&format=csv",
                 headers=H).content.decode("utf-8-sig")
    assert "უშანგი ლაზაშვილი" in body
    assert "ურა ლაბაშვილი" not in body


def test_detail_export_can_omit_the_pos_id(app_ctx):
    """pos=0 yields a sheet in Coca-Cola's identifiers only."""
    ctx = app_ctx
    c = ctx["client"]
    H = ctx["headers"]
    c.post("/api/login", headers=H,
           json={"username": ctx["admin_user"], "password": ctx["admin_pass"]})
    c.post("/api/scan", json={"card_id": "3377269862"})
    c.post("/api/people/roster-import", headers=H,
           files={"file": ("r.xlsx", _roster_xlsx([("077-03174", "ია", "ცუცქირიძე")]),
                           "application/octet-stream")})

    from datetime import date
    d = date.today().isoformat()

    with_pos = c.get(f"/api/reports/export?from={d}&to={d}&format=csv&pos=1",
                     headers=H).content.decode("utf-8-sig")
    assert "3377269862" in with_pos and "077-03174" in with_pos

    without = c.get(f"/api/reports/export?from={d}&to={d}&format=csv&pos=0",
                    headers=H).content.decode("utf-8-sig")
    assert "077-03174" in without and "ია ცუცქირიძე" in without
    assert "3377269862" not in without, "POS id leaked into the Coca-Cola sheet"
    assert "ბარათის ID" not in without


def test_unreadable_roster_file_is_reported_not_a_500(app_ctx):
    """A wrong/corrupt file must produce a Georgian message, not a crash."""
    ctx = app_ctx
    c = ctx["client"]
    H = ctx["headers"]
    c.post("/api/login", headers=H,
           json={"username": ctx["admin_user"], "password": ctx["admin_pass"]})

    r = c.post("/api/people/roster-import", headers=H,
               files={"file": ("notes.xlsx", b"this is not a spreadsheet",
                               "application/octet-stream")})
    assert r.status_code == 422
    assert "ფაილი" in r.json()["detail"]


def test_missing_xlrd_explains_itself(monkeypatch):
    """A kiosk on new code with old deps must say what to run, not traceback.

    quick-start.bat now installs requirements, but an already-running kiosk can
    still hit this window, and ModuleNotFoundError tells the operator nothing.
    """
    import builtins

    from app import roster

    real_import = builtins.__import__

    def no_xlrd(name, *args, **kwargs):
        if name == "xlrd":
            raise ImportError("No module named 'xlrd'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_xlrd)
    with pytest.raises(roster.RosterFormatError) as exc:
        roster._rows_from_xls(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
    assert "start.bat" in str(exc.value)


def test_admin_card_list_shows_roster_name_and_code(app_ctx):
    """The card list must identify people, not just show bare numbers."""
    ctx = app_ctx
    c = ctx["client"]
    H = ctx["headers"]
    c.post("/api/login", headers=H,
           json={"username": ctx["admin_user"], "password": ctx["admin_pass"]})
    c.post("/api/people/roster-import", headers=H,
           files={"file": ("r.xlsx", _roster_xlsx([("077-03174", "ია", "ცუცქირიძე")]),
                           "application/octet-stream")})
    c.post("/api/scan", json={"card_id": "3377269862"})   # on the roster
    c.post("/api/scan", json={"card_id": "1234567890"})   # not on it

    listed = {p["card_id"]: p for p in c.get("/api/people", headers=H).json()}

    known = listed["3377269862"]
    assert known["full_name"] == "ია ცუცქირიძე"
    assert known["cc_code"] == "077-03174"
    assert known["from_roster"] is True

    # A card Coca-Cola does not know still shows its code, with a blank name
    # the operator can fill in by hand.
    unknown = listed["1234567890"]
    assert unknown["full_name"] == ""
    assert unknown["cc_code"] == "150-00722"
    assert unknown["from_roster"] is False


def test_day_view_carries_name_and_code(app_ctx):
    ctx = app_ctx
    c = ctx["client"]
    H = ctx["headers"]
    c.post("/api/login", headers=H,
           json={"username": ctx["admin_user"], "password": ctx["admin_pass"]})
    c.post("/api/people/roster-import", headers=H,
           files={"file": ("r.xlsx", _roster_xlsx([("099-48774", "ნონა", "გვრიტიშვილი")]),
                           "application/octet-stream")})
    c.post("/api/scan", json={"card_id": "3378757254"})

    from datetime import date
    d = date.today().isoformat()
    row = c.get(f"/api/reports/day?date={d}", headers=H).json()["rows"][0]
    assert row["full_name"] == "ნონა გვრიტიშვილი"
    assert row["cc_code"] == "099-48774"
    assert row["card_id"] == "3378757254"
    assert row["times"]
