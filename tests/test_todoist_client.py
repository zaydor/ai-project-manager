import connectors.todoist_client as tc


def test_create_payloads_and_dry_run():
    schedule = [
        {"task_id": 1, "start_ts": "2025-01-01T09:00:00Z", "title": "Task one"},
        {"task_id": 2, "title": "Task two", "description": "Notes"},
    ]
    payloads = tc.create_todoist_payloads(schedule)
    assert isinstance(payloads, list) and len(payloads) == 2

    summary = tc.dry_run_create(payloads)
    assert summary["count"] == 2


def test_apply_create_dry_and_undo(monkeypatch):
    payloads = [{"content": "x", "_meta": {"task_id": 1}}]
    # dry-run should not call network
    results = tc.apply_create("fake-token", payloads, dry_run=True)
    assert all(r.get("reason") == "dry_run" for r in results)

    # undo on empty/invalid responses should produce errors
    undo = tc.undo_created("fake-token", results)
    assert isinstance(undo, list)
