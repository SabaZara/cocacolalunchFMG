from datetime import datetime, timezone

from sqlmodel import Session, select

from app.models import Person, ReceiptJob, TapLog, RosterEntry
from app import receipt


def test_receipt_names_repeat_denial_and_midnight(app_ctx, monkeypatch):
    ctx = app_ctx
    # Keep the background worker idle: queue receipts directly for deterministic tests.
    import threading
    monkeypatch.setattr(receipt, 'enabled', lambda: threading.current_thread().name != 'receipt-printer')
    from app.cardcode import pos_to_cc
    card = '0573856032'
    with Session(ctx['db'].engine) as session:
        session.add(Person(card_id=card, full_name='Fallback', daily_limit=1))
        session.add(RosterEntry(cc_code=pos_to_cc(card), full_name='გიორგი მაისურაძე'))
        session.commit()
        for index, day in enumerate((5, 5, 5, 6), 1):
            tap = TapLog(card_id=card, status='ALLOWED' if index in (1, 4) else 'DENIED',
                         reason='' if index in (1, 4) else 'დღის ლიმიტი ამოიწურა',
                         tapped_at=datetime(2026, 9, day, 8, 30, tzinfo=timezone.utc),
                         local_date=datetime(2026, 9, day).date())
            session.add(tap)
            session.flush()
            receipt.queue_receipt(session, tap)
        session.commit()
        jobs = session.exec(select(ReceiptJob).order_by(ReceiptJob.id)).all()
        assert 'გიორგი მაისურაძე' in jobs[0].body
        assert jobs[0].body.startswith(receipt.RECEIPT_HEADER + '\n\n')
        assert '12:30:00' in jobs[0].body
        assert 'დღის რიგითი № 1' in jobs[0].body
        assert 'დღეს ბარათი მეორედ არის გამოყენებული' in jobs[1].body
        assert 'უარყოფილია — კვება არ გაიცა' in jobs[1].body
        assert 'გამოყენებულია 3-ჯერ' in jobs[2].body
        assert 'დღეს გატარება № 1' in jobs[3].body
        assert 'დღის რიგითი № 1' in jobs[3].body


def test_queue_in_scan_and_unknown_name(app_ctx, monkeypatch):
    # Enable queue creation only inside the scan thread; avoid real hardware.
    import threading
    monkeypatch.setattr(receipt, 'enabled', lambda: threading.current_thread().name == 'MainThread')
    with Session(app_ctx['db'].engine) as session:
        result = app_ctx['scan_service'].decide_scan(session, 'test-card')
        assert result.status == 'ALLOWED'
        job = session.exec(select(ReceiptJob)).one()
        assert 'არაიდენტიფიცირებული' in job.body
        assert 'test-card' in job.body


def test_spool_failure_does_not_retry_or_change_meal(app_ctx):
    engine = app_ctx['db'].engine
    with Session(engine) as session:
        session.add(ReceiptJob(tap_id=123, body='ქართულად'))
        session.commit()
    calls = []
    def broken(body, title):
        calls.append(body)
        raise RuntimeError('Printer unavailable')
    assert receipt.process_next(engine, broken)
    assert not receipt.process_next(engine, broken)
    assert calls == ['ქართულად']
    with Session(engine) as session:
        job = session.exec(select(ReceiptJob)).one()
        assert job.state == 'failed'
        assert 'Printer unavailable' in job.error


def test_queue_error_preserves_tap_and_meal(app_ctx, monkeypatch):
    def broken(*args):
        raise RuntimeError('Outbox failure')
    monkeypatch.setattr(receipt, 'queue_receipt', broken)
    with Session(app_ctx['db'].engine) as session:
        result = app_ctx['scan_service'].decide_scan(session, 'test-card')
        assert result.status == 'ALLOWED'
        assert session.exec(select(TapLog)).one().status == 'ALLOWED'


def _enable_queue(monkeypatch):
    import threading
    monkeypatch.setattr(receipt, 'enabled', lambda: threading.current_thread().name != 'receipt-printer')


def test_disabled_and_empty_input(app_ctx, monkeypatch):
    with Session(app_ctx['db'].engine) as session:
        app_ctx['scan_service'].decide_scan(session, '00001234')
        assert session.exec(select(ReceiptJob)).all() == []
        _enable_queue(monkeypatch)
        app_ctx['scan_service'].decide_scan(session, '   ')
        assert session.exec(select(ReceiptJob)).all() == []
        app_ctx['scan_service'].decide_scan(session, '00001234')
        job = session.exec(select(ReceiptJob)).one()
        assert 'დღის რიგითი № 2' in job.body
        assert 'დღეს გატარება № 2' in job.body
        assert 'ბარათი: 00001234' in job.body


def test_denial_manual_name_and_immutable_snapshot(app_ctx, monkeypatch):
    _enable_queue(monkeypatch)
    with Session(app_ctx['db'].engine) as session:
        person = Person(card_id='manual', full_name='თამარ გიორგაძე', active=False)
        session.add(person)
        session.commit()
        result = app_ctx['scan_service'].decide_scan(session, 'manual')
        assert result.status == 'DENIED'
        job = session.exec(select(ReceiptJob)).one()
        assert 'თამარ გიორგაძე' in job.body
        assert 'ბარათი გათიშულია' in job.body
        assert 'უარყოფილია — კვება არ გაიცა' in job.body
        person.full_name = 'Changed name'
        session.add(person)
        session.commit()
        session.refresh(job)
        assert 'თამარ გიორგაძე' in job.body


def test_concurrent_scans_receipt_numbering(app_ctx, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from collections import Counter
    import time

    _enable_queue(monkeypatch)
    now = datetime(2026, 9, 5, 8, 30, tzinfo=timezone.utc)
    monkeypatch.setattr(app_ctx['scan_service'], 'utc_now', lambda: now)
    engine = app_ctx['db'].engine
    total = 240
    started = time.monotonic()
    def tap(index):
        with Session(engine) as session:
            return app_ctx['scan_service'].decide_scan(session, f'card-{index % 12}').status
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert list(pool.map(tap, range(total))) == ['ALLOWED'] * total
    with Session(engine) as session:
        jobs = session.exec(select(ReceiptJob).order_by(ReceiptJob.id)).all()
        assert len(jobs) == total
        assert len(session.exec(select(TapLog)).all()) == total
        sequences, per_card = [], Counter()
        for job in jobs:
            lines = job.body.splitlines()
            sequences.append(int(next(line for line in lines if line.startswith('დღის რიგითი №')).split('№ ')[1]))
            card = next(line for line in lines if line.startswith('ბარათი: '))
            per_card[card] += 1
            assert f'დღეს გატარება № {per_card[card]}' in lines
        assert sequences == list(range(1, total + 1))
        assert set(per_card.values()) == {20}
    print(f'Concurrent scan stress: {total} scans, 8 clients, {time.monotonic() - started:.2f}s')


def test_slow_printer_does_not_block_scan_api(app_ctx, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    _enable_queue(monkeypatch)
    entered, release = Event(), Event()
    engine = app_ctx['db'].engine
    with Session(engine) as session:
        session.add(ReceiptJob(tap_id=999, body='First job'))
        session.commit()
    def slow(*args):
        entered.set()
        assert release.wait(10)
    with ThreadPoolExecutor(max_workers=1) as pool:
        running = pool.submit(receipt.process_next, engine, slow)
        try:
            assert entered.wait(3)
            result = app_ctx['client'].post('/api/scan', json={'card_id': 'next-card'})
            assert result.status_code == 200
            assert result.json()['status'] == 'ALLOWED'
            assert not running.done()
            with Session(engine) as session:
                assert len(session.exec(select(ReceiptJob)).all()) == 2
        finally:
            release.set()
        assert running.result()


def test_restart_preserves_pending_and_never_replays_uncertain(app_ctx):
    from sqlmodel import create_engine
    engine = app_ctx['db'].engine
    with Session(engine) as session:
        for index, state in enumerate(['submitted', 'sending', 'failed', 'pending'], 1):
            session.add(ReceiptJob(tap_id=index, body=state, state=state))
        session.commit()
    fresh_engine = create_engine(app_ctx['settings'].db_url)
    calls = []
    try:
        assert receipt.process_next(fresh_engine, lambda body, title: calls.append(body))
        assert not receipt.process_next(fresh_engine, lambda *args: calls.append('duplicate'))
        assert calls == ['pending']
    finally:
        fresh_engine.dispose()


def test_competing_workers_submit_each_receipt_once(app_ctx):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Lock
    engine = app_ctx['db'].engine
    with Session(engine) as session:
        for i in range(60):
            session.add(ReceiptJob(tap_id=i + 1, body=str(i)))
        session.commit()
    calls, lock = [], Lock()
    def printer(body, title):
        with lock:
            calls.append(int(body))
    def drain():
        while receipt.process_next(engine, printer):
            pass
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: drain(), range(8)))
    assert sorted(calls) == list(range(60))
    with Session(engine) as session:
        assert {job.state for job in session.exec(select(ReceiptJob))} == {'submitted'}


def test_db_error_while_preparing_receipt_preserves_tap(app_ctx, monkeypatch):
    from sqlalchemy import text
    def broken(session, tap):
        session.execute(text('INSERT INTO nonexistent_receipt_table VALUES (1)'))
    monkeypatch.setattr(receipt, 'queue_receipt', broken)
    with Session(app_ctx['db'].engine) as session:
        assert app_ctx['scan_service'].decide_scan(session, 'test-card').status == 'ALLOWED'
        assert session.exec(select(TapLog)).one().status == 'ALLOWED'


def test_meal_log_and_receipt_share_one_midnight_timestamp(app_ctx, monkeypatch):
    from app.models import Scan
    _enable_queue(monkeypatch)
    # 19:59:59 UTC is 23:59:59 in Tbilisi; another clock read would be tomorrow.
    before = datetime(2026, 9, 5, 19, 59, 59, tzinfo=timezone.utc)
    after = datetime(2026, 9, 5, 20, 0, 0, tzinfo=timezone.utc)
    calls = []
    def clock():
        calls.append(True)
        return before if len(calls) == 1 else after
    monkeypatch.setattr(app_ctx['scan_service'], 'utc_now', clock)
    with Session(app_ctx['db'].engine) as session:
        result = app_ctx['scan_service'].decide_scan(session, 'midnight-card')
        tap = session.exec(select(TapLog)).one()
        meal = session.exec(select(Scan)).one()
        job = session.exec(select(ReceiptJob)).one()
        assert len(calls) == 1
        assert meal.local_date == tap.local_date == before.date()
        assert 'თარიღი: 05.09.2026' in job.body
        assert f'გატარების დრო: {result.scanned_at}' in job.body
        assert result.scanned_at == '23:59:59'
        app_ctx['scan_service'].decide_scan(session, 'midnight-card')
        latest = session.exec(select(ReceiptJob).order_by(ReceiptJob.id.desc())).first()
        assert 'თარიღი: 06.09.2026' in latest.body
        assert 'დღეს გატარება № 1' in latest.body
        assert 'დღის რიგითი № 1' in latest.body
