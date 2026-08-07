"""Card (people) management API. Gated by the tunnel middleware (remote-only).

Works with card_id only; name/department are kept in the DB but not surfaced.
"""
from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from ..config import get_settings
from ..db import get_session
from ..importer import import_cards
from ..models import NAME_PLACEHOLDER, Person, Scan
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
    daily_limit: int       # meals allowed per day
    # Present but hidden in the UI for now (kept so re-enabling is trivial).
    full_name: str
    department: str | None = None


class PersonCreate(BaseModel):
    card_id: str
    active: bool = True
    daily_limit: int | None = None


class PersonUpdate(BaseModel):
    card_id: str | None = None
    active: bool | None = None
    full_name: str | None = None
    department: str | None = None
    daily_limit: int | None = None


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


def _to_out(p: Person, ate_count: int) -> PersonOut:
    return PersonOut(
        id=p.id,
        card_id=p.card_id,
        active=p.active,
        ate_today=ate_count > 0,
        ate_count=ate_count,
        daily_limit=int(p.daily_limit),
        full_name=p.full_name,
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
    return [_to_out(p, counts.get(p.id, 0)) for p in people]


@router.post("", response_model=PersonOut, status_code=201)
def create_person(
    payload: PersonCreate,
    session: Session = Depends(get_session),
) -> PersonOut:
    card_id = normalize_card_id(payload.card_id)
    if not card_id:
        raise HTTPException(status_code=422, detail="ბარათის ID სავალდებულოა.")
    person = Person(card_id=card_id, full_name=NAME_PLACEHOLDER, active=payload.active)
    if payload.daily_limit is not None:
        person.daily_limit = max(int(payload.daily_limit), 0)
    session.add(person)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail=DUPLICATE_MSG)
    session.refresh(person)
    return _to_out(person, 0)


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
        person.daily_limit = max(int(payload.daily_limit), 0)

    session.add(person)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail=DUPLICATE_MSG)
    session.refresh(person)
    counts = _ate_today_counts(session)
    return _to_out(person, counts.get(person.id, 0))


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
        # top up to the daily limit
        need = max(int(person.daily_limit) - len(todays), 0)
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
    return _to_out(person, counts.get(person.id, 0))


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


@router.post("/import")
async def import_people(
    file: UploadFile,
    session: Session = Depends(get_session),
) -> dict:
    data = await file.read()
    report = import_cards(session, file.filename or "", data)
    return report.as_dict()


# ----------------------------- bulk operations ----------------------------- #
class BulkRequest(BaseModel):
    action: str            # delete | activate | deactivate | ate | unate | setlimit
    ids: list[int] | None = None
    all: bool = False      # apply to every card (ignores ids)
    value: int | None = None  # for setlimit: the new daily limit


_BULK_ACTIONS = {"delete", "activate", "deactivate", "ate", "unate", "setlimit"}


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

    elif req.action in ("ate", "unate"):
        tz = get_settings().tz
        now = utc_now()
        today = local_date_for(now, tz)
        for p in people:
            todays = session.exec(
                select(Scan).where(Scan.person_id == p.id, Scan.local_date == today)
            ).all()
            if req.action == "ate":
                need = max(int(p.daily_limit) - len(todays), 0)
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

    elif req.action == "setlimit":
        new_limit = max(int(req.value or 0), 0)
        for p in people:
            if p.daily_limit != new_limit:
                p.daily_limit = new_limit
                session.add(p)
                affected += 1
        session.commit()

    return {"ok": True, "action": req.action, "affected": affected}


@router.get("/export.csv")
def export_people_csv(session: Session = Depends(get_session)) -> Response:
    """Export the full card list (id, status, today's meals, limit) as Georgian CSV."""
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
            int(p.daily_limit),
        ])
    body = buf.getvalue().encode("utf-8-sig")  # BOM so Excel shows Georgian
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="cards.csv"'},
    )
