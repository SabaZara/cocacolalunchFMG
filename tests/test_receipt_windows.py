"""Exercise GDI adapter with a recording Windows API double, without printing.

These check API lifecycle and layout; actual Windows/driver/paper QA is separate.
"""
import sys
from types import SimpleNamespace

import pytest

from app.receipt import print_text


@pytest.fixture
def gdi(monkeypatch):
    monkeypatch.setenv('RECEIPT_PRINTER', 'HPRT test printer')
    class DC:
        def __init__(self):
            self.calls = []
            self.fail = set()
            self.caps = {1: 576, 2: 1600, 3: 203}
            self.font = None
            self.output = []
        def call(self, name, *args):
            self.calls.append((name, args))
            if name in self.fail:
                raise RuntimeError(name)
        def CreatePrinterDC(self, name): self.call('CreatePrinterDC', name)
        def GetDeviceCaps(self, cap): return self.caps[cap]
        def SelectObject(self, font): self.font = font
        def GetTextExtent(self, text):
            return (len(text) * (17 if self.font.get('weight') else 15), 31)
        def StartDoc(self, title): self.call('StartDoc', title)
        def StartPage(self): self.call('StartPage')
        def TextOut(self, x, y, text):
            self.call('TextOut', x, y, text)
            self.output.append((x, y, text, self.font))
        def EndPage(self): self.call('EndPage')
        def EndDoc(self): self.call('EndDoc')
        def AbortDoc(self): self.call('AbortDoc')
        def DeleteDC(self): self.call('DeleteDC')
    dc = DC()
    monkeypatch.setitem(sys.modules, 'win32con', SimpleNamespace(HORZRES=1, VERTRES=2, LOGPIXELSY=3))
    monkeypatch.setitem(sys.modules, 'win32ui', SimpleNamespace(CreateDC=lambda: dc, CreateFont=lambda spec: spec))
    return dc


@pytest.mark.parametrize('dpi,width,height', [(203, 576, 1600), (300, 850, 2400)])
def test_georgian_wrapping_and_bold_warning(gdi, dpi, width, height):
    gdi.caps = {1: width, 2: height, 3: dpi}
    body = 'სახელი და გვარი: ' + 'გიორგი მაისურაძე ' * 4 + '\nდღეს ბარათი მეორედ არის გამოყენებული\nუარყოფილია — კვება არ გაიცა'
    print_text(body)
    assert ''.join(item[2] for item in gdi.output) == body.replace('\n', '')
    assert any(item[3].get('weight') == 700 for item in gdi.output)
    for x, y, text, font in gdi.output:
        gdi.SelectObject(font)
        assert x + gdi.GetTextExtent(text)[0] <= width
        assert y + round(dpi * 15 / 72) <= height
    names = [call[0] for call in gdi.calls]
    assert names[-3:] == ['EndPage', 'EndDoc', 'DeleteDC']
    assert names.count('StartDoc') == names.count('StartPage') == 1
    assert 'AbortDoc' not in names
    assert gdi.calls[0] == ('CreatePrinterDC', ('HPRT test printer',))


@pytest.mark.parametrize('method', ['CreatePrinterDC', 'StartDoc', 'StartPage', 'TextOut', 'EndPage', 'EndDoc'])
def test_driver_failure_cleans_up(gdi, method):
    gdi.fail.add(method)
    with pytest.raises(RuntimeError, match=method):
        print_text('ქართული ტექსტი')
    names = [call[0] for call in gdi.calls]
    assert names[-1] == 'DeleteDC'
    assert ('AbortDoc' in names) == (method not in {'CreatePrinterDC', 'StartDoc'})


def test_abort_failure_still_releases_device_context(gdi):
    gdi.fail.update({'TextOut', 'AbortDoc'})
    with pytest.raises(RuntimeError):
        print_text('ქართული ტექსტი')
    assert gdi.calls[-1][0] == 'DeleteDC'


def test_paper_too_short_never_starts_print(gdi):
    gdi.caps[2] = 50
    with pytest.raises(RuntimeError, match='paper height'):
        print_text('ქართული ტექსტი\n' * 20)
    assert not any(call[0] == 'StartDoc' for call in gdi.calls)
    assert gdi.calls[-1][0] == 'DeleteDC'


def test_invalid_paper_size_never_starts_print(gdi):
    gdi.caps[1] = 0
    with pytest.raises(RuntimeError, match='invalid paper dimensions'):
        print_text('ქართული ტექსტი')
    assert not any(call[0] == 'StartDoc' for call in gdi.calls)


def test_no_default_printer_fallback(gdi, monkeypatch):
    monkeypatch.delenv('RECEIPT_PRINTER')
    with pytest.raises(RuntimeError, match='RECEIPT_PRINTER'):
        print_text('ქართული ტექსტი')
    assert gdi.calls == []
