"""Deterministic scheduler utilities.

Functions:
- create_schedule(tasks, availability, block_min=25, block_max=90, buffer_ratio=0.25)

Behavior:
- Does not split tasks. Tasks with duration > block_max are flagged with split_recommended=True
- Uses greedy bin-packing to balance day workloads deterministically.
- Returns a list of schedule entries with day index and start/end times (ISO strings if start_date provided).

Tasks input: sequence of dicts with at least:
    - id (any)
    - estimate_hours (float) OR estimate_minutes (int)

Availability: dict with keys:
    - hours_per_day (float, default 4)
    - start_date (ISO date string, optional) used as day 0 date (UTC)

All outputs are deterministic for a given input.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional


def _to_minutes(task: Dict[str, Any]) -> int:
    if "estimate_minutes" in task and task["estimate_minutes"] is not None:
        return int(task["estimate_minutes"])
    if "estimate_hours" in task and task["estimate_hours"] is not None:
        return int(round(float(task["estimate_hours"]) * 60))
    # default 60 minutes
    return 60


def create_schedule(
    tasks: Iterable[Dict[str, Any]],
    availability: Dict[str, Any],
    block_min: int = 25,
    block_max: int = 90,
    buffer_ratio: float = 0.25,
) -> List[Dict[str, Any]]:
    """Create a deterministic schedule for tasks using greedy bin-packing.

    Parameters:
    - tasks: iterable of task dicts (must contain 'id' and estimate_hours or estimate_minutes)
    - availability: {'hours_per_day': float, 'start_date': 'YYYY-MM-DD' (optional)}
    - block_min/block_max: minutes boundaries for blocks (do not split tasks)
    - buffer_ratio: fraction of day reserved as buffer (0.0-1.0)

    Returns list of entries:
      {
        'task_id': ..., 'day': int, 'start_min': int, 'end_min': int, 'duration_min': int,
        'split_recommended': bool, 'start_ts': optional ISO str, 'end_ts': optional ISO str
      }
    """
    # Normalize inputs to list for deterministic iteration
    task_list = [dict(t) for t in tasks]

    hours_per_day = float(availability.get("hours_per_day", 4))
    capacity_per_day = int(round(hours_per_day * 60 * (1.0 - float(buffer_ratio))))
    if capacity_per_day <= 0:
        raise ValueError("availability results in non-positive capacity; adjust hours_per_day or buffer_ratio")

    # Convert tasks to (id, minutes, original)
    converted = []
    for t in task_list:
        minutes = _to_minutes(t)
        # apply minimal block granularity
        if minutes < block_min:
            minutes = block_min
        converted.append({"id": t.get("id"), "minutes": int(minutes), "orig": t})

    # Sort by descending minutes, then by id for deterministic tie-break
    converted.sort(key=lambda x: (-x["minutes"], str(x["id"])))

    # Days represented as dicts: {'load': int, 'tasks': [entries]}
    days: List[Dict[str, Any]] = []

    # Greedy place each task into the day with smallest current load that still fits.
    for item in converted:
        placed = False
        candidate_day_idx = None
        # Consider days in increasing load order deterministically
        order = sorted(range(len(days)), key=lambda i: (days[i]["load"], i))
        for di in order:
            if days[di]["load"] + item["minutes"] <= capacity_per_day:
                candidate_day_idx = di
                break

        if candidate_day_idx is None:
            # create a new day
            days.append({"load": 0, "tasks": []})
            candidate_day_idx = len(days) - 1

        day = days[candidate_day_idx]
        start_min = day["load"]
        end_min = start_min + item["minutes"]
        day["tasks"].append({
            "task_id": item["id"],
            "start_min": start_min,
            "end_min": end_min,
            "duration_min": item["minutes"],
            "split_recommended": item["minutes"] > block_max,
        })
        day["load"] += item["minutes"]

    # Flatten results and add optional ISO timestamps
    start_date = availability.get("start_date")
    base_date = None
    if start_date:
        # parse date (YYYY-MM-DD)
        base_date = datetime.fromisoformat(start_date)

    result: List[Dict[str, Any]] = []
    for di, d in enumerate(days):
        for t in d["tasks"]:
            entry = dict(t)
            entry["day"] = di
            if base_date is not None:
                day_start = base_date + timedelta(days=di)
                # treat start_min as minutes from 00:00 of that day (UTC naive)
                start_ts = day_start + timedelta(minutes=entry["start_min"])
                end_ts = day_start + timedelta(minutes=entry["end_min"])
                entry["start_ts"] = start_ts.isoformat()
                entry["end_ts"] = end_ts.isoformat()
            result.append(entry)

    # Sort result by day and start_min for determinism
    result.sort(key=lambda r: (r["day"], r["start_min"], str(r.get("task_id"))))
    return result
