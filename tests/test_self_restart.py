"""Regression checks for restart helpers surviving their parent app shutdown."""
from types import SimpleNamespace
import io
import json
import os

from scripts import self_restart as sr


def test_windows_restart_does_not_kill_its_own_process_tree(tmp_path, monkeypatch):
    monkeypatch.setattr(sr, 'IS_WINDOWS', True)
    pids = tmp_path / 'pids.txt'
    pids.write_text(f'app 100 python run.py\nproxy 200 python tunnel_proxy.py\napp {os.getpid()} self_restart.py\n')
    monkeypatch.setattr(sr, 'PIDS', pids)
    monkeypatch.setattr(sr, '_port_from_env', lambda: 8000)
    monkeypatch.setattr(sr.time, 'sleep', lambda seconds: None)
    calls = []
    def run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[0] == 'netstat':
            return SimpleNamespace(stdout='\n'.join([
                'TCP 127.0.0.1:8000 0.0.0.0:0 LISTENING 101',
                'TCP 127.0.0.1:8001 0.0.0.0:0 LISTENING 201',
                'TCP 127.0.0.1:9999 0.0.0.0:0 LISTENING 999',
                'TCP 127.0.0.1:50000 127.0.0.1:8000 ESTABLISHED 555']))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(sr.subprocess, 'run', run)
    sr._kill_old()
    kills = [cmd for cmd in calls if cmd[0] == 'taskkill']
    assert all('/T' not in cmd for cmd in kills)
    killed = {int(cmd[cmd.index('/PID') + 1]) for cmd in kills if '/PID' in cmd}
    assert killed == {100, 101, 200, 201}
    assert os.getpid() not in killed
    assert not pids.exists()


def test_missing_pid_file_still_stops_actual_windows_listener(tmp_path, monkeypatch):
    monkeypatch.setattr(sr, 'IS_WINDOWS', True)
    monkeypatch.setattr(sr, 'PIDS', tmp_path / 'missing.txt')
    monkeypatch.setattr(sr, '_port_from_env', lambda: 8000)
    monkeypatch.setattr(sr, '_listener_pids', lambda ports: {321})
    monkeypatch.setattr(sr, '_kill_stray_ngrok', lambda: None)
    monkeypatch.setattr(sr.time, 'sleep', lambda seconds: None)
    calls = []
    monkeypatch.setattr(sr.subprocess, 'run', lambda cmd, **kwargs: calls.append(cmd))
    sr._kill_old()
    assert calls == [['taskkill', '/PID', '321', '/F']]


def test_health_check_waits_for_new_process_instance(monkeypatch):
    import urllib.request
    clock = [0]
    monkeypatch.setattr(sr.time, 'time', lambda: clock[0])
    monkeypatch.setattr(sr.time, 'sleep', lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    instances = iter(['old-process', 'new-process'])
    seen = []
    def open_url(url, **kwargs):
        if url.endswith('/api/version'):
            instance = next(instances)
            seen.append(instance)
            response = io.BytesIO(json.dumps({'version':'2.5.1', 'instance_id':instance}).encode())
        else:
            response = io.BytesIO(b'{"ok":true}')
        response.status = 200
        return response
    monkeypatch.setattr(urllib.request, 'urlopen', open_url)
    assert sr._healthy(8000, seconds=3, expected_version='2.5.1', expected_instance='new-process')
    assert seen == ['old-process', 'new-process']
    assert clock[0] == 1


def test_old_healthy_process_is_not_restart_success(monkeypatch):
    import urllib.request
    clock = [0]
    monkeypatch.setattr(sr.time, 'time', lambda: clock[0])
    monkeypatch.setattr(sr.time, 'sleep', lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    def open_url(url, **kwargs):
        response = io.BytesIO(b'{"version":"2.4.0","instance_id":"old"}')
        response.status = 200
        return response
    monkeypatch.setattr(urllib.request, 'urlopen', open_url)
    assert not sr._healthy(8000, seconds=2, expected_instance='new')
