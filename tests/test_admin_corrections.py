from datetime import date
from sqlmodel import Session, select
from app.models import Scan
from test_tap_log import _login, _roster_xlsx


def test_edit_roster_name_and_card_preserves_history(app_ctx):
    c, h = app_ctx['client'], app_ctx['headers']
    _login(app_ctx)
    c.post('/api/people/roster-import', headers=h,
           files={'file': ('roster.xlsx', _roster_xlsx([('077-03174', 'ძველი', 'გვარი')]))})
    c.post('/api/scan', json={'card_id': '3377269862'})
    person = c.get('/api/people', headers=h).json()[0]
    url = f"/api/people/{person['id']}"
    result = c.put(url, headers=h, json={'full_name': 'ახალი გვარი', 'card_id': '3377269862'})
    assert result.json()['full_name'] == 'ახალი გვარი'
    assert not result.json()['from_roster']
    # A later roster import must not silently undo the explicit correction.
    c.post('/api/people/roster-import', headers=h,
           files={'file': ('roster.xlsx', _roster_xlsx([('077-03174', 'სხვა', 'გვარი')]))})
    assert c.get('/api/people', headers=h).json()[0]['full_name'] == 'ახალი გვარი'
    c.post('/api/people', headers=h, json={'card_id': '00123'})
    assert c.put(url, headers=h, json={'card_id': '00123', 'full_name': 'არ შეინახო'}).status_code == 409
    assert c.get('/api/people', headers=h).json()[1]['full_name'] == 'ახალი გვარი'
    assert c.put(url, headers=h, json={'card_id': '00456'}).json()['card_id'] == '00456'
    with Session(app_ctx['db'].engine) as session:
        assert session.exec(select(Scan)).one().card_id == '3377269862'


def test_mistaken_tap_removes_only_its_meal_once(app_ctx):
    c, h = app_ctx['client'], app_ctx['headers']
    _login(app_ctx)
    for _ in range(2):
        c.post('/api/scan', json={'card_id': '3377269862'})
    day = date.today().isoformat()
    url = f'/api/reports/taplog?from={day}&to={day}'
    rows = c.get(url, headers=h).json()['rows']
    correction = f"/api/reports/taplog/{rows[0]['id']}/mistaken"
    assert c.post(correction, headers=h).status_code == 200
    assert c.post(correction, headers=h).status_code == 200
    assert c.get('/api/people', headers=h).json()[0]['ate_count'] == 1
    log = c.get(url, headers=h).json()
    assert log['total'] == 2
    assert log['rows'][0]['mistaken'] is True
    assert log['rows'][0]['reason'] == 'შეცდომით დაფიქსირებული'
    assert log['rows'][1]['mistaken'] is False
    assert c.post('/api/reports/taplog/999999/mistaken', headers=h).status_code == 404
    c.post('/api/logout', headers=h)
    assert c.post(correction, headers=h).status_code == 401


def test_restore_original_day_after_card_edit_and_repeat(app_ctx):
    from app.models import TapLog
    from datetime import timedelta
    c, h = app_ctx['client'], app_ctx['headers']
    _login(app_ctx)
    c.post('/api/scan', json={'card_id': '2987654321'})
    with Session(app_ctx['db'].engine) as session:
        tap = session.exec(select(TapLog)).one()
        meal = session.exec(select(Scan)).one()
        previous = tap.local_date - timedelta(days=1)
        tap.local_date = meal.local_date = previous
        tap_id, person_id = tap.id, meal.person_id
        session.add(tap)
        session.add(meal)
        session.commit()
    base = f'/api/reports/taplog/{tap_id}'
    assert c.post(base + '/mistaken', headers=h).status_code == 200
    assert c.put(f'/api/people/{person_id}', headers=h,
                 json={'card_id': '2987654322'}).status_code == 200
    for _ in range(2):
        assert c.post(base + '/restore', headers=h).status_code == 200
    with Session(app_ctx['db'].engine) as session:
        restored = session.exec(select(Scan)).one()
        assert restored.person_id == person_id
        assert restored.card_id == '2987654321'
        assert restored.local_date == previous
        assert session.get(TapLog, tap_id).mistaken is False
    assert c.post(base + '/mistaken', headers=h).status_code == 200
    assert c.post(base + '/restore', headers=h).status_code == 200
    with Session(app_ctx['db'].engine) as session:
        assert len(session.exec(select(Scan)).all()) == 1
    c.post('/api/logout', headers=h)
    assert c.post(base + '/restore', headers=h).status_code == 401


def test_restore_denied_does_not_create_meal(app_ctx):
    from app.models import TapLog
    c, h = app_ctx['client'], app_ctx['headers']
    _login(app_ctx)
    c.post('/api/scan', json={'card_id': ''})
    with Session(app_ctx['db'].engine) as session:
        tap_id = session.exec(select(TapLog)).one().id
    base = f'/api/reports/taplog/{tap_id}'
    assert c.post(base + '/mistaken', headers=h).status_code == 200
    assert c.post(base + '/restore', headers=h).status_code == 200
    with Session(app_ctx['db'].engine) as session:
        assert session.exec(select(Scan)).all() == []
        assert session.get(TapLog, tap_id).status == 'DENIED'
        assert session.get(TapLog, tap_id).mistaken is False


def test_restore_deleted_person_fails_without_reassigning_meal(app_ctx):
    from app.models import TapLog
    c, h = app_ctx['client'], app_ctx['headers']
    _login(app_ctx)
    c.post('/api/scan', json={'card_id': '2987654321'})
    with Session(app_ctx['db'].engine) as session:
        tap_id = session.exec(select(TapLog)).one().id
        person_id = session.exec(select(Scan)).one().person_id
    base = f'/api/reports/taplog/{tap_id}'
    assert c.post(base + '/mistaken', headers=h).status_code == 200
    c.delete(f'/api/people/{person_id}', headers=h)
    # SQLite may reuse a deleted row ID; the new owner must not get this meal.
    c.post('/api/people', headers=h, json={'card_id': '2987654321'})
    assert c.post(base + '/restore', headers=h).status_code == 409
    with Session(app_ctx['db'].engine) as session:
        assert session.get(TapLog, tap_id).mistaken is True


def test_restore_legacy_mark_and_previously_cleared_meal(app_ctx):
    from app.models import TapLog
    c, h = app_ctx['client'], app_ctx['headers']
    _login(app_ctx)
    c.post('/api/scan', json={'card_id': '2987654321'})
    with Session(app_ctx['db'].engine) as session:
        tap = session.exec(select(TapLog)).one()
        tap_id = tap.id
        tap.mistaken = True
        session.add(tap)
        session.delete(session.exec(select(Scan)).one())
        session.commit()
    base = f'/api/reports/taplog/{tap_id}'
    assert c.post(base + '/restore', headers=h).status_code == 200
    with Session(app_ctx['db'].engine) as session:
        meal = session.exec(select(Scan)).one()
        session.delete(meal)
        session.commit()
    assert c.post(base + '/mistaken', headers=h).status_code == 200
    assert c.post(base + '/restore', headers=h).status_code == 200
    with Session(app_ctx['db'].engine) as session:
        assert session.exec(select(Scan)).all() == []
