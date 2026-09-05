"""Windows setup: python -m scripts.receipt_printer --list / --check / --test / --status."""
import argparse
import os

from sqlmodel import Session, select

from app.config import get_settings
from app.models import ReceiptJob
from app.receipt import print_text
from app import receipt_config


def main():
    get_settings()  # Load the project's .env.
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--list', action='store_true')
    group.add_argument('--test', action='store_true')
    group.add_argument('--check', action='store_true', help='Check driver/dependency without printing')
    group.add_argument('--status', action='store_true')
    args = parser.parse_args()
    if args.list:
        import win32print
        for entry in win32print.EnumPrinters(2 | 4):
            print(entry[2])
    elif args.check:
        import win32print
        import win32ui
        import win32con
        name = receipt_config.read()['printer']
        if not name:
            parser.error('Set RECEIPT_PRINTER in .env first')
        handle = win32print.OpenPrinter(name)
        try:
            info = win32print.GetPrinter(handle, 2)
            print(f"Printer: {name}\nDriver: {info['pDriverName']}\nPort: {info['pPortName']}")
        finally:
            win32print.ClosePrinter(handle)
        dc = win32ui.CreateDC()
        try:
            dc.CreatePrinterDC(name)
            width = dc.GetDeviceCaps(win32con.HORZRES)
            height = dc.GetDeviceCaps(win32con.VERTRES)
            dpi_x = dc.GetDeviceCaps(win32con.LOGPIXELSX)
            dpi_y = dc.GetDeviceCaps(win32con.LOGPIXELSY)
            if min(width, height, dpi_x, dpi_y) <= 0:
                raise RuntimeError('Invalid printer paper dimensions')
            print(f'Printable area: {width / dpi_x * 25.4:.1f} x {height / dpi_y * 25.4:.1f} mm')
            print(f'Resolution: {dpi_x} x {dpi_y} DPI')
        finally:
            dc.DeleteDC()
        print('Driver check passed. Run --test and inspect actual paper before enabling.')
    elif args.test:
        print_text('საცდელი ჩეკი\nსახელი და გვარი: გიორგი მაისურაძე\n'
                   'თარიღი: 05.09.2026\nგატარების დრო: 12:30:00\n'
                   'დღის რიგითი № 2\nდღეს გატარება № 2\n'
                   'დღეს ბარათი მეორედ არის გამოყენებული\n'
                   'ნებადართულია\nეს არის ტესტი', 'LUNCH printer test')
        print('Submitted to Windows. Check the paper for Georgian text and clipping.')
    else:
        from app.db import engine, init_db
        init_db()
        with Session(engine) as session:
            for job in session.exec(select(ReceiptJob).order_by(ReceiptJob.id.desc()).limit(20)):
                print(f'{job.id}: {job.state} {job.error}')


if __name__ == '__main__':
    main()
