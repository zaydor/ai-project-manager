import backend.db as db


def test_init_and_crud(tmp_path, monkeypatch):
    # point DB_FILE to a temp file to avoid touching repo DB
    tmp_db = tmp_path / "data.sqlite3"
    monkeypatch.setattr(db, "DB_FILE", tmp_db)

    # initialize and perform simple CRUD
    db.init_db()
    pid = db.insert_project("Test project summary")
    assert isinstance(pid, int) and pid > 0

    mids = db.insert_milestones(pid, [{"name": "M1", "target_date": "2025-01-01"}])
    assert len(mids) == 1

    tids = db.insert_tasks(pid, [{"milestone_id": mids[0], "name": "T1", "estimate_hours": 1.5, "dependencies": []}])
    assert len(tids) == 1

    proj = db.fetch_project(pid)
    assert proj is not None and proj["summary"] == "Test project summary"

    tasks = db.list_tasks(pid)
    assert len(tasks) == 1

    mstones = db.list_milestones(pid)
    assert len(mstones) == 1
