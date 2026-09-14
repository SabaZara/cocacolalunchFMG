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
