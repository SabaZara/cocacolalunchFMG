"""Reports API. Gated by the tunnel middleware (remote-only)."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlmodel import Session

from .. import reports as R
from ..db import get_session
from ..security import get_current_admin

router = APIRouter(
    prefix="/api/reports",
    tags=["reports"],
    dependencies=[Depends(get_current_admin)],
)


def _parse_date(s: str, field: str) -> date:
    try:
        return date.fromisoformat(s)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"არასწორი თარიღი ({field}).")


def _check_range(frm: date, to: date) -> None:
    if frm > to:
        raise HTTPException(status_code=422, detail="საწყისი თარიღი ბოლოზე გვიანია.")


@router.get("/today")
def today(session: Session = Depends(get_session)) -> dict:
    return R.today_summary(session)


@router.get("/daily")
def daily(
    frm: str = Query(alias="from"),
    to: str = Query(alias="to"),
    session: Session = Depends(get_session),
) -> dict:
    f, t = _parse_date(frm, "from"), _parse_date(to, "to")
    _check_range(f, t)
    return {"from": f.isoformat(), "to": t.isoformat(), "rows": R.daily_counts(session, f, t)}


@router.get("/day")
def day(
    date_str: str = Query(alias="date"),
    window: int | None = Query(default=None),
    session: Session = Depends(get_session),
) -> dict:
    d = _parse_date(date_str, "date")
    if window not in (None, 1, 2):
        raise HTTPException(status_code=422, detail="არასწორი კვების ფანჯარა.")
    rows, w1, w2 = R.day_detail(session, d, window)
    return {
        "date": d.isoformat(),
        "people": len(rows),                      # distinct people (in filter)
        "meals": sum(r.count for r in rows),      # meals shown (in filter)
        "w1": w1,                                 # whole-day window totals
        "w2": w2,
        "rows": [
            {"card_id": r.card_id, "count": r.count, "times": r.times}
            for r in rows
        ],
    }


@router.get("/quant")
def quant(
    frm: str = Query(alias="from"),
    to: str = Query(alias="to"),
    session: Session = Depends(get_session),
) -> dict:
    f, t = _parse_date(frm, "from"), _parse_date(to, "to")
    _check_range(f, t)
    return R.quantitative(session, f, t)


@router.get("/quant-export")
def quant_export(
    frm: str = Query(alias="from"),
    to: str = Query(alias="to"),
    format: str = Query(default="xlsx"),
    session: Session = Depends(get_session),
) -> Response:
    from urllib.parse import quote

    f, t = _parse_date(frm, "from"), _parse_date(to, "to")
    _check_range(f, t)
    data = R.quantitative(session, f, t)
    ext = "csv" if format == "csv" else "xlsx"
    if ext == "csv":
        body = R.quantitative_csv(data)
        media = "text/csv; charset=utf-8"
    else:
        body = R.quantitative_xlsx(data)
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    # Georgian download name (RFC 5987 filename*), ASCII fallback for old agents.
    span = f.isoformat() if f == t else f"{f.isoformat()}_{t.isoformat()}"
    ka_name = quote(f"რაოდენობრივი რეპორტი_{span}.{ext}")
    ascii_name = _filename("quant", f, t, ext)
    return Response(
        content=body,
        media_type=media,
        headers={
            "Content-Disposition":
                f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{ka_name}"
        },
    )


def _filename(prefix: str, frm: date, to: date, ext: str) -> str:
    if frm == to:
        return f"{prefix}_{frm.isoformat()}.{ext}"
    return f"{prefix}_{frm.isoformat()}_{to.isoformat()}.{ext}"


@router.get("/export")
def export_detail(
    frm: str = Query(alias="from"),
    to: str = Query(alias="to"),
    format: str = Query(default="xlsx"),
    session: Session = Depends(get_session),
) -> Response:
    f, t = _parse_date(frm, "from"), _parse_date(to, "to")
    _check_range(f, t)
    rows = R.detail_rows(session, f, t)
    if format == "csv":
        body = R.detail_csv(rows)
        media = "text/csv; charset=utf-8"
        fname = _filename("detail", f, t, "csv")
    else:
        body = R.detail_xlsx(rows)
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        fname = _filename("detail", f, t, "xlsx")
    return Response(
        content=body,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/attendance")
def export_attendance(
    frm: str = Query(alias="from"),
    to: str = Query(alias="to"),
    format: str = Query(default="xlsx"),
    session: Session = Depends(get_session),
) -> Response:
    f, t = _parse_date(frm, "from"), _parse_date(to, "to")
    _check_range(f, t)
    data = R.attendance(session, f, t)
    if format == "csv":
        body = R.attendance_csv(data)
        media = "text/csv; charset=utf-8"
        fname = _filename("attendance", f, t, "csv")
    else:
        body = R.attendance_xlsx(data)
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        fname = _filename("attendance", f, t, "xlsx")
    return Response(
        content=body,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
