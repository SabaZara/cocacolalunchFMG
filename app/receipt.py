"""Persistent receipt outbox and Windows driver printing (no browser dialogs)."""
from __future__ import annotations

import logging
from threading import Event

from sqlalchemy import func, update
from sqlmodel import Session, select

from .models import NAME_PLACEHOLDER, Person, ReceiptJob, TapLog
from .config import get_settings
from .timeutil import to_local
from . import receipt_config

log = logging.getLogger(__name__)


def enabled() -> bool:
    return receipt_config.read()["enabled"]


def queue_receipt(session: Session, tap: TapLog) -> None:
    """Called after tap flush, while SQLite holds its write lock. No commit."""
    from .cardcode import pos_to_cc
    from .roster import lookup_name

    if not enabled() or not tap.card_id:
        return
    day_filter = (TapLog.local_date == tap.local_date, TapLog.id <= tap.id,
                  TapLog.card_id != "")
    sequence = session.exec(select(func.count()).select_from(TapLog).where(*day_filter)).one()
    uses = session.exec(select(func.count()).select_from(TapLog).where(
        *day_filter, TapLog.card_id == tap.card_id)).one()
    person = session.exec(select(Person).where(Person.card_id == tap.card_id)).first()
    name = lookup_name(session, pos_to_cc(tap.card_id))
    if not name and person:
        typed = (person.full_name or "").strip()
        name = typed if typed != NAME_PLACEHOLDER else ""
    local = to_local(tap.tapped_at, get_settings().tz)
    lines = ["კვების ჩეკი", f"დღის რიგითი № {sequence}",
             f"სახელი და გვარი: {name or 'არაიდენტიფიცირებული'}",
             f"ბარათი: {tap.card_id}", f"თარიღი: {local:%d.%m.%Y}",
             f"გატარების დრო: {local:%H:%M:%S}", f"დღეს გატარება № {uses}"]
    if uses == 2:
        lines.append("დღეს ბარათი მეორედ არის გამოყენებული")
    elif uses > 2:
        lines.append(f"დღეს ბარათი გამოყენებულია {uses}-ჯერ")
    lines.append("ნებადართულია" if tap.status == "ALLOWED" else "უარყოფილია — კვება არ გაიცა")
    if tap.reason:
        lines.append(tap.reason)
    lines.append(f"ჩეკის ID: {tap.id}")
    session.add(ReceiptJob(tap_id=tap.id, body="\n".join(lines)))


def print_text(body: str, title: str = "LUNCH receipt", printer_name: str | None = None) -> None:
    """Use Unicode GDI text and the explicitly selected Windows printer."""
    import win32con
    import win32ui

    printer = printer_name if printer_name is not None else receipt_config.read()["printer"]
    if not printer:
        raise RuntimeError("Set RECEIPT_PRINTER to the installed Windows printer name")
    dc = win32ui.CreateDC()
    started = False
    try:
        dc.CreatePrinterDC(printer)
        width = dc.GetDeviceCaps(win32con.HORZRES)
        height = dc.GetDeviceCaps(win32con.VERTRES)
        dpi = dc.GetDeviceCaps(win32con.LOGPIXELSY)
        if width <= 0 or height <= 0 or dpi <= 0:
            raise RuntimeError("Printer driver returned invalid paper dimensions")
        font = win32ui.CreateFont({"name": "Sylfaen", "height": -round(dpi * 11 / 72)})
        bold_font = win32ui.CreateFont({"name": "Sylfaen", "height": -round(dpi * 11 / 72),
                                       "weight": 700})
        margin = max(4, round(dpi * 2 / 25.4))
        line_height = round(dpi * 15 / 72)
        # Wrap by actual rendered width, including long names/card IDs.
        wrapped = []
        for line in body.splitlines():
            emphasis = line.startswith(("დღეს ბარათი", "უარყოფილია"))
            dc.SelectObject(bold_font if emphasis else font)
            current = ""
            for char in line:
                if current and dc.GetTextExtent(current + char)[0] > width - 2 * margin:
                    wrapped.append((current, emphasis))
                    current = ""
                current += char
            wrapped.append((current, emphasis))
        if margin * 2 + len(wrapped) * line_height > height:
            raise RuntimeError("Receipt exceeds configured paper height; select a longer 80mm form")
        dc.StartDoc(title)
        started = True
        dc.StartPage()
        for index, (line, emphasis) in enumerate(wrapped):
            dc.SelectObject(bold_font if emphasis else font)
            dc.TextOut(margin, margin + index * line_height, line)
        dc.EndPage()
        dc.EndDoc()
        started = False
    finally:
        try:
            if started:
                dc.AbortDoc()
        finally:
            dc.DeleteDC()


def process_next(engine, printer=None) -> bool:
    """Claim before sending. Never automatically resend an uncertain job."""
    with Session(engine) as session:
        job = session.exec(select(ReceiptJob).where(ReceiptJob.state == "pending")
                           .order_by(ReceiptJob.id)).first()
        if job is None:
            return False
        job_id, body = job.id, job.body
        claimed = session.execute(update(ReceiptJob).where(
            ReceiptJob.id == job_id, ReceiptJob.state == "pending").values(state="sending"))
        session.commit()
        if claimed.rowcount != 1:
            return True
    try:
        (printer or print_text)(body, f"LUNCH receipt {job_id}")
        state, error = "submitted", ""
    except Exception as exc:
        log.exception("Receipt %s could not be submitted", job_id)
        state, error = "failed", str(exc)[:500]
    with Session(engine) as session:
        session.execute(update(ReceiptJob).where(ReceiptJob.id == job_id)
                        .values(state=state, error=error))
        session.commit()
    return True


def worker(stop: Event, engine) -> None:
    while not stop.is_set():
        try:
            if enabled() and process_next(engine):
                continue
        except Exception:
            log.exception("Receipt worker error")
        stop.wait(1)
