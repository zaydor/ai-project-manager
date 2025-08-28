"""Small demo CLI to print schedule JSON.

Usage:
  python scripts/demo_schedule.py [tasks.json]

If tasks.json is omitted, a sample set is used.
"""

import json
import sys

from agent_controller.scheduler import create_schedule


def main():
    if len(sys.argv) > 1:
        with open(sys.argv[1], "r") as fh:
            tasks = json.load(fh)
    else:
        tasks = [
            {"id": 1, "estimate_hours": 2, "title": "Design DB"},
            {"id": 2, "estimate_hours": 3, "title": "Implement API"},
            {"id": 3, "estimate_hours": 1, "title": "Write tests"},
        ]
    sched = create_schedule(tasks, {"hours_per_day": 4, "start_date": "2025-09-01"})
    print(json.dumps(sched, indent=2))


if __name__ == "__main__":
    main()
