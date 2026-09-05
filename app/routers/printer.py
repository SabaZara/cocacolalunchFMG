"""Authenticated remote printer setup; never changes cards or meal records."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlmodel import Session, select

from .. import receipt, receipt_config
from ..db import get_session
from ..models import ReceiptJob
from ..security import get_current_admin

router = APIRouter(prefix="/api/printer", tags=["printer"],
                   dependencies=[Depends(get_current_admin)])


def installed_printers() -> list[str]:
    try:
        import win32print
        return sorted({entry[2] for entry in win32print.EnumPrinters(2 | 4)})
    except Exception as exc:
        raise HTTPException(503, "პრინტერების სია ვერ ჩაიტვირთა. საჭიროა Windows, ბეჭდვის კომპონენტი და დრაივერი.") from exc


class PrinterSettings(BaseModel):
    printer: str = Field(default="", max_length=256)
    enabled: bool = False


@router.get("")
def status(session: Session = Depends(get_session)) -> dict:
    result = receipt_config.read()
    try:
        result.update(printers=installed_printers(), error="")
    except HTTPException as exc:
        result.update(printers=[], error=exc.detail)
    result["queue"] = {state: count for state, count in session.exec(
        select(ReceiptJob.state, func.count()).group_by(ReceiptJob.state)).all()}
    return result


@router.post("")
def configure(payload: PrinterSettings) -> dict:
    name = payload.printer.strip()
    # Disabling must work even when the printer/driver is unavailable.
    if payload.enabled and name not in installed_printers():
        raise HTTPException(422, "აირჩიეთ დაყენებული პრინტერი.")
    return receipt_config.save(name, payload.enabled)


@router.post("/test")
def test_print(payload: PrinterSettings) -> dict:
    name = payload.printer.strip()
    if not name or name not in installed_printers():
        raise HTTPException(422, "აირჩიეთ დაყენებული პრინტერი.")
    try:
        receipt.print_text("საცდელი ჩეკი\nსახელი და გვარი: გიორგი მაისურაძე\n"
                           "დღის რიგითი № 2\nდღეს გატარება № 2\n"
                           "დღეს ბარათი მეორედ არის გამოყენებული\n"
                           "ნებადართულია\nეს არის ტესტი — კვება არ აღირიცხება",
                           "LUNCH printer test", printer_name=name)
    except Exception as exc:
        raise HTTPException(503, f"საცდელი ბეჭდვა ვერ მოხერხდა: {exc}") from exc
    return {"ok": True, "message": "ჩეკი გაგზავნილია. შეამოწმეთ ქართული ტექსტი და ქაღალდის ჭრა პრინტერზე."}


@router.post("/install")
def install_component() -> dict:
    from scripts.ensure_printer_support import ensure
    return ensure()
