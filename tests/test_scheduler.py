import pytest

from agent_controller.scheduler import create_schedule


def test_basic_schedule_respects_buffer():
    tasks = [
        {"id": 1, "estimate_hours": 2},
        {"id": 2, "estimate_hours": 2},
        {"id": 3, "estimate_hours": 2},
    ]
    # 4 hours/day with 25% buffer -> capacity = 3 hours = 180 minutes
    sched = create_schedule(
        tasks, {"hours_per_day": 4, "start_date": "2025-01-01"}, buffer_ratio=0.25
    )
    # total minutes scheduled per day should be <= 180
    day0 = [s for s in sched if s["day"] == 0]
    assert sum(s["duration_min"] for s in day0) <= 180


def test_no_split_behavior_for_short_tasks():
    tasks = [
        {"id": "a", "estimate_minutes": 20},
        {"id": "b", "estimate_minutes": 20},
    ]
    # block_min defaults to 25, so each task should be rounded up to 25 and scheduled
    sched = create_schedule(tasks, {"hours_per_day": 1}, block_min=25)
    assert all(s["duration_min"] >= 25 for s in sched)


def test_long_task_flagged_but_not_split():
    tasks = [
        {"id": "long", "estimate_minutes": 200},
        {"id": "small", "estimate_minutes": 30},
    ]
    sched = create_schedule(tasks, {"hours_per_day": 4}, block_max=90)
    long_entries = [s for s in sched if s["task_id"] == "long"]
    assert len(long_entries) == 1
    assert long_entries[0]["split_recommended"] is True


def test_zero_capacity_raises():
    tasks = [{"id": 1, "estimate_hours": 1}]
    with pytest.raises(ValueError):
        create_schedule(
            tasks, {"hours_per_day": 1, "start_date": "2025-01-01"}, buffer_ratio=1.0
        )


def test_exact_fit_and_many_small_tasks():
    # hours_per_day 2, buffer 0 -> capacity 120 minutes
    tasks = [{"id": i, "estimate_minutes": 10} for i in range(12)]
    # use buffer_ratio=0.0 so full 2 hours/day == 120 minutes are available
    sched = create_schedule(
        tasks,
        {"hours_per_day": 2, "start_date": "2025-01-01"},
        block_min=10,
        buffer_ratio=0.0,
    )
    # should fit exactly into one day (120 minutes)
    day0 = [s for s in sched if s["day"] == 0]
    assert sum(s["duration_min"] for s in day0) == 120
