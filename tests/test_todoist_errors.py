import time

import connectors.todoist_client as tc


class Resp:
    def __init__(self, status_code=200, json_data=None, text="", raise_on_json=False):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text
        self.headers = {}
        self._raise = raise_on_json

    def json(self):
        if self._raise:
            raise ValueError("bad json")
        return self._json


def test_5xx_exhausts_retries(monkeypatch):
    def always_500(method, url, headers=None, json=None, timeout=None):
        return Resp(status_code=500, json_data={"err": "server"})

    monkeypatch.setattr(tc, "requests", type("R", (), {"request": always_500}))
    monkeypatch.setattr(time, "sleep", lambda s: None)

    ok, resp = tc._request_with_retry(
        "POST", tc.TODOIST_TASKS_URL, headers={}, json_payload={}
    )
    assert ok is False
    assert isinstance(resp, dict) and resp.get("error") == "max_retries_exceeded"


def test_malformed_json_returns_none(monkeypatch):
    def resp_bad_json(method, url, headers=None, json=None, timeout=None):
        return Resp(status_code=200, raise_on_json=True)

    monkeypatch.setattr(tc, "requests", type("R", (), {"request": resp_bad_json}))

    ok, resp = tc._request_with_retry(
        "GET", tc.TODOIST_TASKS_URL, headers={}, json_payload=None
    )
    assert ok is True
    assert resp is None


def test_status_204_returns_true_none(monkeypatch):
    def resp_204(method, url, headers=None, json=None, timeout=None):
        return Resp(status_code=204, json_data=None)

    monkeypatch.setattr(tc, "requests", type("R", (), {"request": resp_204}))

    ok, resp = tc._request_with_retry(
        "DELETE", tc.TODOIST_TASKS_URL + "/1", headers={}, json_payload=None
    )
    assert ok is True
    assert resp is None
