import connectors.calendar_client as cc
import time


def test_apply_create_events_max_retries(monkeypatch):
    # Simulate build returning a service whose events().insert().execute() always raises HttpError
    class AlwaysFailEvents:
        def insert(self, calendarId, body):
            class Inserter:
                def execute(inner):
                    raise cc.HttpError("permanent")

            return Inserter()

    class FailService:
        def events(self):
            return AlwaysFailEvents()

    def fake_build(name, ver, credentials=None):
        return FailService()

    monkeypatch.setattr(cc, "build", fake_build)
    monkeypatch.setattr(cc, "_HAS_GOOGLEAPI", True)
    monkeypatch.setattr(time, "sleep", lambda s: None)

    events = [{"summary": "x"}]
    res = cc.apply_create_events(object(), events, dry_run=False)
    assert isinstance(res, list)
    # Should be an unsuccessful response due to repeated HttpError
    assert res[0]["success"] is False
