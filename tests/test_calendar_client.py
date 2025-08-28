import connectors.calendar_client as cc


def test_make_event_objects_and_dry_run():
    schedule = [
        {
            "task_id": 1,
            "start_ts": "2025-01-01T09:00:00Z",
            "end_ts": "2025-01-01T10:00:00Z",
            "title": "Meet",
        }
    ]
    events = cc.make_event_objects(schedule)
    assert isinstance(events, list) and len(events) == 1
    assert events[0]["start"]["dateTime"] == "2025-01-01T09:00:00Z"

    preview = cc.dry_run_create_events(events)
    assert preview["count"] == 1


def test_apply_create_events_dry_run():
    events = [{"summary": "x"}]
    res = cc.apply_create_events(None, events, dry_run=True)
    assert (
        isinstance(res, list)
        and res[0]["reason"] == "dry_run"
        or res[0].get("success") is False
    )
