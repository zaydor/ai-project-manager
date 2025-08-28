import time

import connectors.calendar_client as cc


class FakeHttpError(Exception):
    pass


def test_request_with_retry_success_after_http_error(monkeypatch):
    # Create a fake service where first call raises, second returns a dict
    class FakeEvents:
        def insert(self, calendarId, body):
            class Inserter:
                def __init__(self, parent):
                    self._p = parent

                def execute(inner):
                    # toggle state
                    if not hasattr(FakeEvents, "called"):
                        FakeEvents.called = True
                        raise cc.HttpError("fake http error")
                    return {"id": "evt123"}

            return Inserter(self)

    class FakeService:
        def events(self):
            return FakeEvents()

    def fake_build(name, ver, credentials=None):
        return FakeService()

    monkeypatch.setattr(cc, "build", fake_build)
    monkeypatch.setattr(cc, "_HAS_GOOGLEAPI", True)
    monkeypatch.setattr(time, "sleep", lambda s: None)

    # call apply_create_events with dry_run=False and a dummy credentials object
    events = [{"summary": "x"}]
    res = cc.apply_create_events(object(), events, dry_run=False)
    assert isinstance(res, list)
    assert res[0]["success"] is True
