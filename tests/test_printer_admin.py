from types import SimpleNamespace

from sqlmodel import Session, select

from app import receipt, receipt_config
from app.models import ReceiptJob, Scan, TapLog


def login(ctx):
    ctx['client'].post('/api/login', headers=ctx['headers'], json={
        'username': ctx['admin_user'], 'password': ctx['admin_pass']})


def test_remote_printer_setup_preserves_db_and_takes_effect_without_restart(app_ctx, monkeypatch):
    import app.routers.printer as api
    monkeypatch.setattr(api, 'installed_printers', lambda: ['HPRT TP80BE'])
    captured = []
    monkeypatch.setattr(receipt, 'print_text', lambda *a, **kw: captured.append((a, kw)))
    client, headers = app_ctx['client'], app_ctx['headers']
    login(app_ctx)
    assert client.get('/api/printer', headers=headers).json()['enabled'] is False
    result = client.post('/api/printer/test', headers=headers, json={'printer': 'HPRT TP80BE'})
    assert result.status_code == 200
    assert captured[0][1]['printer_name'] == 'HPRT TP80BE'
    with Session(app_ctx['db'].engine) as session:
        for model in (Scan, TapLog, ReceiptJob):
            assert session.exec(select(model)).all() == []
    assert client.post('/api/printer', headers=headers,
                       json={'printer': 'HPRT TP80BE', 'enabled': True}).status_code == 200
    assert receipt.enabled() is True
    assert receipt_config.read()['printer'] == 'HPRT TP80BE'
    assert client.post('/api/scan', json={'card_id': 'test-card'}).status_code == 200
    with Session(app_ctx['db'].engine) as session:
        assert session.exec(select(ReceiptJob)).one().body
    client.post('/api/printer', headers=headers, json={'printer': 'HPRT TP80BE', 'enabled': False})
    assert receipt.enabled() is False


def test_printer_endpoints_require_tunnel_and_login(app_ctx):
    client = app_ctx['client']
    for path in ['/api/printer', '/api/printer/test', '/api/printer/install']:
        assert client.post(path, json={}).status_code == 403
        assert client.post(path, headers=app_ctx['headers'], json={}).status_code == 401
    assert client.get('/api/printer').status_code == 403
    assert client.get('/api/printer', headers=app_ctx['headers']).status_code == 401


def test_unavailable_printer_cannot_enable_but_can_disable(app_ctx, monkeypatch):
    import app.routers.printer as api
    monkeypatch.setattr(api, 'installed_printers', lambda: [])
    login(app_ctx)
    client, headers = app_ctx['client'], app_ctx['headers']
    assert client.post('/api/printer', headers=headers, json={'printer': 'Missing', 'enabled': True}).status_code == 422
    assert client.post('/api/printer/test', headers=headers, json={'printer': 'Missing'}).status_code == 422
    assert client.post('/api/printer', headers=headers, json={'printer': 'Missing', 'enabled': False}).status_code == 200


def test_printer_component_bootstrap_success_and_failure(monkeypatch):
    from scripts import ensure_printer_support as helper
    monkeypatch.setattr(helper.sys, 'platform', 'win32')
    responses = iter([False, True])
    monkeypatch.setattr(helper, 'available', lambda: next(responses))
    calls = []
    monkeypatch.setattr(helper.subprocess, 'run', lambda cmd, **kw: (
        calls.append((cmd, kw)) or SimpleNamespace(returncode=0)))
    assert helper.ensure()['ok']
    assert calls[0][0][0] == helper.sys.executable
    assert calls[0][0][-1] == 'pywin32==311'
    assert calls[0][1]['timeout'] == 75
    monkeypatch.setattr(helper, 'available', lambda: False)
    def timeout(*args, **kwargs):
        raise helper.subprocess.TimeoutExpired('pip', 75)
    monkeypatch.setattr(helper.subprocess, 'run', timeout)
    assert helper.ensure()['ok'] is False


def test_existing_printer_component_does_not_reinstall(monkeypatch):
    from scripts import ensure_printer_support as helper
    monkeypatch.setattr(helper.sys, 'platform', 'win32')
    monkeypatch.setattr(helper, 'available', lambda: True)
    monkeypatch.setattr(helper.subprocess, 'run', lambda *a, **k: (_ for _ in ()).throw(AssertionError('Unexpected install')))
    assert helper.ensure()['ok']


def test_update_migration_bootstraps_windows_component_without_failing_meals(app_ctx, monkeypatch):
    from scripts import migrate_db, ensure_printer_support
    monkeypatch.setattr(migrate_db.sys, 'platform', 'win32')
    calls = []
    monkeypatch.setattr(ensure_printer_support, 'ensure', lambda: (
        calls.append(True) or {'ok': False, 'error': 'Offline'}))
    assert migrate_db.main() == 0
    assert calls == [True]
    assert app_ctx['client'].post('/api/scan', json={'card_id': 'offline-install'}).json()['status'] == 'ALLOWED'
