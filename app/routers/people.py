"""Card (people) management API. Gated by the tunnel middleware (remote-only).

Works with card_id only; name/department are kept in the DB but not surfaced.

Cards normally appear here on their own: the kiosk registers a card the first
time it taps. Manual add / import still work for pre-loading a known list.
The daily limit is global (app_config), so it is reported per card but is the
same number for all of them and is edited via /api/settings.
"""
from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from .. import app_config as AC
from ..config import get_settings
from ..db import get_session
from ..importer import import_cards
from ..models import NAME_PLACEHOLDER, Person, Scan
from ..roster import names_by_cc_code
from ..scan_service import normalize_card_id
from ..security import get_current_admin
from ..timeutil import local_date_for, utc_now

router = APIRouter(prefix="/api/people", tags=["people"], dependencies=[Depends(get_current_admin)])

DUPLICATE_MSG = "ეს ბარათი უკვე მინიჭებულია."


class PersonOut(BaseModel):
    id: int
    card_id: str
    active: bool
    ate_today: bool        # True if ate_count > 0 (kept for compatibility)
    ate_count: int         # meals claimed today
    daily_limit: int       # the GLOBAL limit — same value for every card
    # The name to SHOW: Coca-Cola's roster if this card is on it, otherwise
    # whatever was typed by hand. Blank when neither exists.
    full_name: str
    # This card's Coca-Cola code, derived from the POS id.
    cc_code: str = ""
    # True when the shown name came from the roster (so the UI can present it
    # as authoritative rather than as an editable free-text value).
    from_roster: bool = False
    department: str | None = None


class PersonCreate(BaseModel):
    card_id: str
    active: bool = True
    # Names can be filled in later; blank means the "----" placeholder.
    full_name: str | None = None
    daily_limit: int | None = None


class PersonUpdate(BaseModel):
    card_id: str | None = None
    active: bool | None = None
    full_name: str | None = None
    department: str | None = None
    # This card's own limit. -1 (UNLIMITED) removes the cap entirely;
    # 0 blocks the card. Omitted = leave unchanged.
    daily_limit: int | None = None


def _clean_limit(value: int) -> int:
    """Validate a per-card limit. UNLIMITED passes through; else clamp 0..MAX."""
    from ..models import UNLIMITED

    v = int(value)
    if v == UNLIMITED or v < 0:
        return UNLIMITED           # any negative means "no limit"
    return min(v, AC.MAX_DAILY_LIMIT)


def _ate_today_counts(session: Session) -> dict[int, int]:
    """person_id -> number of meals claimed today (local)."""
    from sqlalchemy import func

    tz = get_settings().tz
    today = local_date_for(utc_now(), tz)
    rows = session.exec(
        select(Scan.person_id, func.count()).where(Scan.local_date == today)
        .group_by(Scan.person_id)
    ).all()
    return {pid: int(n) for pid, n in rows}


def _to_out(p: Person, ate_count: int, roster: dict[str, str] | None = None) -> PersonOut:
    """Shape one card for the admin list.

    `roster` is the whole {cc_code: name} map, passed in so listing 800 cards
    is one query rather than one per row.
    """
    from ..cardcode import pos_to_cc

    cc = pos_to_cc(p.card_id)
    roster_name = (roster or {}).get(cc, "")
    typed = (p.full_name or "").strip()
    if typed == NAME_PLACEHOLDER:
        typed = ""

    return PersonOut(
        id=p.id,
        card_id=p.card_id,
        active=p.active,
        ate_today=ate_count > 0,
        ate_count=ate_count,
        daily_limit=int(p.daily_limit),     # this card's own limit
        # Coca-Cola's spelling wins; hand-typed is the fallback.
        full_name=roster_name or typed,
        cc_code=cc,
        from_roster=bool(roster_name),
        department=p.department,
    )


@router.get("", response_model=list[PersonOut])
def list_people(
    q: str | None = None,
    session: Session = Depends(get_session),
) -> list[PersonOut]:
    stmt = select(Person)
    if q:
        needle = f"%{q.strip()}%"
        stmt = stmt.where(Person.card_id.like(needle))
    stmt = stmt.order_by(Person.card_id)
    people = session.exec(stmt).all()
    counts = _ate_today_counts(session)
    roster = names_by_cc_code(session)
    return [_to_out(p, counts.get(p.id, 0), roster) for p in people]


@router.post("", response_model=PersonOut, status_code=201)
def create_person(
    payload: PersonCreate,
    session: Session = Depends(get_session),
) -> PersonOut:
    card_id = normalize_card_id(payload.card_id)
    if not card_id:
        raise HTTPException(status_code=422, detail="ბარათის ID სავალდებულოა.")
    person = Person(
        card_id=card_id,
        full_name=(payload.full_name or "").strip() or NAME_PLACEHOLDER,
        active=payload.active,
    )
    if payload.daily_limit is not None:
        person.daily_limit = _clean_limit(payload.daily_limit)
    session.add(person)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail=DUPLICATE_MSG)
    session.refresh(person)
    return _to_out(person, 0, names_by_cc_code(session))


@router.put("/{person_id}", response_model=PersonOut)
def update_person(
    person_id: int,
    payload: PersonUpdate,
    session: Session = Depends(get_session),
) -> PersonOut:
    person = session.get(Person, person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="ბარათი ვერ მოიძებნა.")

    if payload.card_id is not None:
        new_id = normalize_card_id(payload.card_id)
        if not new_id:
            raise HTTPException(status_code=422, detail="ბარათის ID სავალდებულოა.")
        person.card_id = new_id
    if payload.active is not None:
        person.active = payload.active
    if payload.full_name is not None:
        person.full_name = payload.full_name
    if payload.department is not None:
        person.department = payload.department
    if payload.daily_limit is not None:
        person.daily_limit = _clean_limit(payload.daily_limit)

    session.add(person)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail=DUPLICATE_MSG)
    session.refresh(person)
    counts = _ate_today_counts(session)
    return _to_out(person, counts.get(person.id, 0), names_by_cc_code(session))


class AteUpdate(BaseModel):
    ate: bool


@router.post("/{person_id}/ate", response_model=PersonOut)
def set_ate_today(
    person_id: int,
    payload: AteUpdate,
    session: Session = Depends(get_session),
) -> PersonOut:
    """Manually set whether this person has eaten TODAY (local date).

    ate=True  -> fill today's meals up to the person's daily_limit.
    ate=False -> clear ALL of today's meals (count back to 0).
    """
    person = session.get(Person, person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="ბარათი ვერ მოიძებნა.")

    tz = get_settings().tz
    now = utc_now()
    today = local_date_for(now, tz)

    todays = session.exec(
        select(Scan).where(Scan.person_id == person_id, Scan.local_date == today)
    ).all()

    if payload.ate:
        # top up to THIS card's limit (an unlimited card gets one meal)
        from ..models import UNLIMITED

        lim = int(person.daily_limit)
        target = 1 if lim == UNLIMITED else lim
        need = max(target - len(todays), 0)
        for _ in range(need):
            session.add(Scan(person_id=person_id, card_id=person.card_id,
                             scanned_at=now, local_date=today))
        if need:
            session.commit()
    else:
        for s in todays:
            session.delete(s)
        if todays:
            session.commit()

    session.refresh(person)
    counts = _ate_today_counts(session)
    return _to_out(person, counts.get(person.id, 0), names_by_cc_code(session))


@router.delete("/{person_id}")
def delete_person(person_id: int, session: Session = Depends(get_session)) -> Response:
    person = session.get(Person, person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="ბარათი ვერ მოიძებნა.")
    # Remove the person's scan history too (delete = full removal).
    for s in session.exec(select(Scan).where(Scan.person_id == person_id)).all():
        session.delete(s)
    session.flush()  # ensure scans are gone before the FK-referenced person
    session.delete(person)
    session.commit()
    return Response(status_code=204)


class PersonAdd(BaseModel):
    """One person from the admin page, identified EITHER way."""
    identifier: str
    full_name: str | None = None


@router.post("/add", status_code=201)
def add_person(
    payload: PersonAdd,
    session: Session = Depends(get_session),
) -> dict:
    """Add one person by POS card id OR by Coca-Cola code.

    The two identifiers cannot be treated the same way, because POS -> CC is
    one-way (see cardcode): a DDD-DDDDD code names 256 possible POS ids, so it
    can never produce the card row the kiosk matches on.

      * POS id  -> a real card row, usable at the reader immediately. Any name
                   given is stored on the card.
      * CC code -> a roster NAME only. The card itself registers itself the
                   first time it physically taps, and picks this name up then.

    Returned `kind` tells the UI which of the two happened so it can say so.
    """
    from ..cardcode import is_cc_code, normalize_cc_code, pos_to_cc
    from ..roster import upsert_entry

    raw = (payload.identifier or "").strip()
    name = (payload.full_name or "").strip()
    if not raw:
        raise HTTPException(status_code=422, detail="ბარათის ID ან Coca-Cola კოდი სავალდებულოა.")

    # A Coca-Cola code: name-only entry, no card row.
    if is_cc_code(raw) or (normalize_cc_code(raw) and not raw.isdigit()):
        code = normalize_cc_code(raw)
        if not name:
            raise HTTPException(
                status_code=422,
                detail="Coca-Cola კოდით დამატებისას სახელი სავალდებულოა.",
            )
        created = upsert_entry(session, code, name)
        return {
            "kind": "roster",
            "cc_code": code,
            "full_name": name,
            "created": created,
        }

    # Otherwise a POS id: a real card row.
    card_id = normalize_card_id(raw)
    person = Person(
        card_id=card_id,
        full_name=name or NAME_PLACEHOLDER,
        active=True,
    )
    session.add(person)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail=DUPLICATE_MSG)
    session.refresh(person)
    return {
        "kind": "card",
        "id": person.id,
        "card_id": person.card_id,
        "cc_code": pos_to_cc(person.card_id),
        "full_name": name,
        "created": True,
    }


@router.post("/import")
async def import_people(
    file: UploadFile,
    session: Session = Depends(get_session),
) -> dict:
    data = await file.read()
    report = import_cards(session, file.filename or "", data)
    return report.as_dict()


@router.post("/roster-import")
async def import_roster_file(
    file: UploadFile,
    session: Session = Depends(get_session),
) -> dict:
    """Load Coca-Cola's personnel export (CardNo / FirstName / LastName).

    Names then come from Coca-Cola's own records instead of being re-typed,
    matched to each scan by converting the POS id to their DDD-DDDDD code.
    Re-importing refreshes existing entries rather than duplicating them.
    """
    from ..roster import RosterFormatError, import_roster

    data = await file.read()
    try:
        report = import_roster(session, file.filename or "", data)
    except RosterFormatError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:  # noqa: BLE001
        raise HTTPException(
            status_code=422,
            detail="ფაილი ვერ წაიკითხა. დარწმუნდით, რომ ეს არის Coca-Cola-ს "
                   "სია (.xls / .xlsx / .csv) სვეტებით CardNo და სახელი.",
        )
    return report.as_dict()


@router.get("/roster-status")
def roster_status(session: Session = Depends(get_session)) -> dict:
    """How many people the roster holds — shown next to the upload control."""
    from sqlalchemy import func as _f

    from ..models import RosterEntry

    count = session.exec(select(_f.count()).select_from(RosterEntry)).one()
    return {"count": int(count)}


# ----------------------------- bulk operations ----------------------------- #
class BulkRequest(BaseModel):
    action: str            # delete | activate | deactivate | ate | unate | setlimit
    ids: list[int] | None = None
    all: bool = False      # apply to every card (ignores ids)
    # setlimit: the new per-card limit for the targeted cards.
    value: int | None = None


_BULK_ACTIONS = {"delete", "activate", "deactivate", "ate", "unate",
                 "setlimit", "unlimit"}


def _target_people(session: Session, req: BulkRequest) -> list[Person]:
    if req.all:
        return session.exec(select(Person)).all()
    if not req.ids:
        return []
    return session.exec(select(Person).where(Person.id.in_(req.ids))).all()


@router.post("/bulk")
def bulk(req: BulkRequest, session: Session = Depends(get_session)) -> dict:
    if req.action not in _BULK_ACTIONS:
        raise HTTPException(status_code=422, detail="უცნობი მოქმედება.")

    people = _target_people(session, req)
    affected = 0

    if req.action == "delete":
        ids = [p.id for p in people]
        if ids:
            for s in session.exec(select(Scan).where(Scan.person_id.in_(ids))).all():
                session.delete(s)
            # Flush scan deletes FIRST so the FK constraint is satisfied before
            # the people rows are removed.
            session.flush()
            for p in people:
                session.delete(p)
            affected = len(ids)
        session.commit()

    elif req.action in ("activate", "deactivate"):
        want = req.action == "activate"
        for p in people:
            if p.active != want:
                p.active = want
                session.add(p)
                affected += 1
        session.commit()

    elif req.action in ("setlimit", "unlimit"):
        # unlimit removes the cap; setlimit applies a number. Both are per
        # card, so "all" is how you change everybody at once.
        from ..models import UNLIMITED

        new_limit = UNLIMITED if req.action == "unlimit" \
            else _clean_limit(req.value if req.value is not None else 0)
        for p in people:
            if int(p.daily_limit) != new_limit:
                p.daily_limit = new_limit
                session.add(p)
                affected += 1
        session.commit()

    elif req.action in ("ate", "unate"):
        tz = get_settings().tz
        now = utc_now()
        today = local_date_for(now, tz)
        from ..models import UNLIMITED

        for p in people:
            todays = session.exec(
                select(Scan).where(Scan.person_id == p.id, Scan.local_date == today)
            ).all()
            if req.action == "ate":
                # Fill to THIS card's limit. An unlimited card has no cap to
                # fill to, so one meal is what "mark as eaten" can mean.
                lim = int(p.daily_limit)
                target = 1 if lim == UNLIMITED else lim
                need = max(target - len(todays), 0)
                for _ in range(need):
                    session.add(Scan(person_id=p.id, card_id=p.card_id,
                                     scanned_at=now, local_date=today))
                if need:
                    affected += 1
            else:  # unate
                if todays:
                    for s in todays:
                        session.delete(s)
                    affected += 1
        session.commit()

    return {"ok": True, "action": req.action, "affected": affected}


@router.get("/export.csv")
def export_people_csv(session: Session = Depends(get_session)) -> Response:
    """Export the full card list (id, status, today's meals, limit) as Georgian CSV."""
    from ..models import UNLIMITED

    counts = _ate_today_counts(session)
    people = session.exec(select(Person).order_by(Person.card_id)).all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["ბარათის ID", "სტატუსი", "დღეს ნაჭამი", "დღიური ლიმიტი"])
    for p in people:
        w.writerow([
            p.card_id,
            "აქტიური" if p.active else "გათიშული",
            counts.get(p.id, 0),
            "შეუზღუდავი" if int(p.daily_limit) == UNLIMITED else int(p.daily_limit),
        ])
    body = buf.getvalue().encode("utf-8-sig")  # BOM so Excel shows Georgian
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="cards.csv"'},
    )
