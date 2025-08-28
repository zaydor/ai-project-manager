import time

import connectors.todoist_client as tc


class DummyResp:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text
        self.headers = {}

    def json(self):
        return self._json


def test_request_with_retry_handles_429_then_success(monkeypatch):
    calls = {"i": 0}

    def fake_request(method, url, headers=None, json=None, timeout=None):
        i = calls["i"]
        calls["i"] += 1
        if i == 0:
            r = DummyResp(status_code=429, json_data={"error": "rate"})
            r.headers = {"Retry-After": "0"}
            return r
        return DummyResp(status_code=201, json_data={"id": 123})

    monkeypatch.setattr(tc, "requests", type("R", (), {"request": fake_request}))
    monkeypatch.setattr(time, "sleep", lambda s: None)

    ok, resp = tc._request_with_retry("POST", tc.TODOIST_TASKS_URL, headers={"x": "y"}, json_payload={})
    assert ok is True
    assert resp == {"id": 123}


def test_request_with_retry_handles_exceptions_then_success(monkeypatch):
    calls = {"i": 0}

    def fake_request(method, url, headers=None, json=None, timeout=None):
        i = calls["i"]
        calls["i"] += 1
        if i == 0:
            raise RuntimeError("transient")
        return DummyResp(status_code=200, json_data={"ok": True})

    monkeypatch.setattr(tc, "requests", type("R", (), {"request": fake_request}))
    monkeypatch.setattr(time, "sleep", lambda s: None)

    ok, resp = tc._request_with_retry("POST", tc.TODOIST_TASKS_URL, headers={}, json_payload={})
    assert ok is True
    assert resp == {"ok": True}
