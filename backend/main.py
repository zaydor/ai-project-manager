from __future__ import annotations

import logging
import os

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

import db
from models import (
    ApplyRequest,
    ApplyResponse,
    ErrorResponse,
    IntakeRequest,
    IntakeResponse,
    MilestoneModel,
    PlanRequest,
    PlanResponse,
    ScheduledTask,
    SchedulePreviewRequest,
    SchedulePreviewResponse,
    TaskModel,
)
from ollama_client import OllamaClient

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
logger = logging.getLogger("backend")

app = Flask(__name__)

# Initialize DB at startup
db.init_db()
ollama = OllamaClient()


@app.errorhandler(Exception)
def handle_exception(e):  # type: ignore[override]
    if isinstance(e, HTTPException):
        return jsonify(ErrorResponse(error=str(e), detail=e.description).dict()), e.code
    logger.exception("Unhandled error")
    return jsonify(ErrorResponse(error="internal_error", detail=str(e)).dict()), 500


@app.post("/projects/intake")
def project_intake():
    data = request.get_json(force=True, silent=True) or {}
    try:
        payload = IntakeRequest(**data)
    except Exception as e:  # pydantic validation error
        return jsonify(ErrorResponse(error="validation_error", detail=str(e)).dict()), 400

    project_id = db.insert_project(payload.summary)
    questions = ollama.clarifying_questions(payload.summary)
    resp = IntakeResponse(project_id=project_id, clarifying_questions=questions)
    return jsonify(resp.dict())


@app.post("/projects/plan")
def project_plan():
    data = request.get_json(force=True, silent=True) or {}
    try:
        payload = PlanRequest(**data)
    except Exception as e:
        return jsonify(ErrorResponse(error="validation_error", detail=str(e)).dict()), 400

    project = db.fetch_project(payload.project_id)
    if not project:
        return jsonify(ErrorResponse(error="not_found", detail="Project not found").dict()), 404

    # Use answers + original summary to craft plan
    plan_raw = ollama.draft_plan(project["summary"], payload.answers)
    milestone_names = plan_raw.get("milestones", [])
    task_dicts = plan_raw.get("tasks", [])

    milestones = [
        {"name": m_name, "target_date": None}
        for m_name in milestone_names
        if isinstance(m_name, str)
    ]
    milestone_ids = db.insert_milestones(payload.project_id, milestones)
    milestone_map = {name: mid for name, mid in zip([m["name"] for m in milestones], milestone_ids)}

    validated_tasks: list[TaskModel] = []
    db_ready_tasks = []
    for t in task_dicts:
        try:
            est = float(t.get("estimate_hours", 1))
            tm = TaskModel(
                name=str(t.get("name", "Task")),
                estimate_hours=est if est > 0 else 1.0,
                project_id=payload.project_id,
                milestone_id=milestone_map.get(t.get("milestone")),
            )
            validated_tasks.append(tm)
            db_ready_tasks.append(tm.dict())
        except Exception as e:  # skip invalid task
            logger.warning("Skipping task due to validation: %s", e)

    task_ids = db.insert_tasks(payload.project_id, db_ready_tasks)
    for tid, tm in zip(task_ids, validated_tasks):
        tm.id = tid

    milestone_models = [
        MilestoneModel(id=mid, project_id=payload.project_id, name=name)
        for name, mid in milestone_map.items()
    ]
    resp = PlanResponse(
        project_id=payload.project_id,
        milestones=milestone_models,
        tasks=validated_tasks,
        total_estimated_hours=sum(t.estimate_hours for t in validated_tasks),
    )
    return jsonify(resp.dict())


@app.post("/projects/schedule_preview")
def schedule_preview():
    data = request.get_json(force=True, silent=True) or {}
    try:
        payload = SchedulePreviewRequest(**data)
    except Exception as e:
        return jsonify(ErrorResponse(error="validation_error", detail=str(e)).dict()), 400

    # Simple repeated weekly availability map: list of (day, hours)
    availability_order = [a.day for a in payload.availability]
    hours_map = {a.day: a.hours for a in payload.availability}
    if not availability_order:
        return jsonify(ErrorResponse(error="invalid_availability").dict()), 400

    day_index = 0
    schedule: list[ScheduledTask] = []
    for task in payload.tasks:
        remaining = task.estimate_hours
        start_day_index = day_index
        while remaining > 0:
            day_name = availability_order[day_index % len(availability_order)]
            capacity = hours_map[day_name]
            allocate = min(capacity, remaining)
            remaining -= allocate
            if remaining > 0:
                day_index += 1
            else:
                # Done
                end_day_index = day_index
                schedule.append(
                    ScheduledTask(
                        task_name=task.name,
                        start_day_index=start_day_index,
                        end_day_index=end_day_index,
                        allocated_hours=task.estimate_hours,
                    )
                )
        day_index += 1  # move to next day for next task

    resp = SchedulePreviewResponse(
        project_id=payload.project_id,
        schedule=schedule,
        total_days=max((t.end_day_index for t in schedule), default=0) + 1 if schedule else 0,
    )
    return jsonify(resp.dict())


def perform_external_writes(
    tasks: list[TaskModel], do_todoist: bool, do_calendar: bool
) -> list[str]:
    actions: list[str] = []
    if do_todoist:
        # TODO: integrate real Todoist API using TODOIST_API_TOKEN
        actions.append(f"Would create {len(tasks)} Todoist tasks")
    if do_calendar:
        # TODO: integrate Google Calendar events using service account credentials
        actions.append("Would create calendar events (1 per task)")
    return actions


@app.post("/projects/apply")
def apply_plan():
    data = request.get_json(force=True, silent=True) or {}
    try:
        payload = ApplyRequest(**data)
    except Exception as e:
        return jsonify(ErrorResponse(error="validation_error", detail=str(e)).dict()), 400

    project = db.fetch_project(payload.project_id)
    if not project:
        return jsonify(ErrorResponse(error="not_found", detail="Project not found").dict()), 404

    actions: list[str] = []
    external_writes = False
    if not payload.dry_run and payload.confirm:
        actions = perform_external_writes(
            payload.tasks, payload.push_todoist, payload.push_calendar
        )
        external_writes = True
    else:
        actions = perform_external_writes(
            payload.tasks, payload.push_todoist, payload.push_calendar
        )
        actions = [f"DRY-RUN: {a}" for a in actions]

    resp = ApplyResponse(
        project_id=payload.project_id,
        actions=actions,
        dry_run=payload.dry_run,
        confirmed=payload.confirm,
        external_writes_performed=external_writes,
        metadata={"task_count": len(payload.tasks)},
    )
    return jsonify(resp.dict())


def run():
    # Bind to localhost only for 'local-only' guarantee; override via HOST env if needed.
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "5000"))
    logger.info("Starting Flask app on %s:%s", host, port)
    app.run(host=host, port=port)


if __name__ == "__main__":
    run()
