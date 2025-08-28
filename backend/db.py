from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

DB_FILE = Path(__file__).parent / "data.sqlite3"


def init_db() -> None:
    with sqlite3.connect(DB_FILE) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                summary TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS milestones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                target_date TEXT,
                FOREIGN KEY(project_id) REFERENCES projects(id)
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                milestone_id INTEGER,
                name TEXT NOT NULL,
                estimate_hours REAL NOT NULL,
                dependencies TEXT,
                FOREIGN KEY(project_id) REFERENCES projects(id),
                FOREIGN KEY(milestone_id) REFERENCES milestones(id)
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS schedule (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                task_id INTEGER NOT NULL,
                start_day_index INTEGER NOT NULL,
                end_day_index INTEGER NOT NULL,
                allocated_hours REAL NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id),
                FOREIGN KEY(task_id) REFERENCES tasks(id)
            );
            """
        )
        conn.commit()


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_FILE)
    try:
        yield conn
    finally:
        conn.close()


def insert_project(summary: str) -> int:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO projects (summary) VALUES (?)", (summary,))
        conn.commit()
        return int(cur.lastrowid)


def insert_milestones(project_id: int, milestones: Iterable[Dict[str, Any]]) -> List[int]:
    ids: List[int] = []
    with get_conn() as conn:
        cur = conn.cursor()
        for m in milestones:
            cur.execute(
                "INSERT INTO milestones (project_id, name, target_date) VALUES (?, ?, ?)",
                (project_id, m.get("name"), m.get("target_date")),
            )
            ids.append(int(cur.lastrowid))
        conn.commit()
    return ids


def insert_tasks(project_id: int, tasks: Iterable[Dict[str, Any]]) -> List[int]:
    ids: List[int] = []
    with get_conn() as conn:
        cur = conn.cursor()
        for t in tasks:
            cur.execute(
                """
                INSERT INTO tasks (project_id, milestone_id, name, estimate_hours, dependencies)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    t.get("milestone_id"),
                    t.get("name"),
                    t.get("estimate_hours"),
                    ",".join(t.get("dependencies", [])),
                ),
            )
            ids.append(int(cur.lastrowid))
        conn.commit()
    return ids


def fetch_project(project_id: int) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, summary, created_at FROM projects WHERE id=?", (project_id,))
        row = cur.fetchone()
        if not row:
            return None
        return {"id": row[0], "summary": row[1], "created_at": row[2]}


def list_tasks(project_id: int) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, milestone_id, name, estimate_hours, dependencies FROM tasks WHERE project_id=?",
            (project_id,),
        )
        rows = cur.fetchall()
        out: List[Dict[str, Any]] = []
        for r in rows:
            out.append(
                {
                    "id": r[0],
                    "milestone_id": r[1],
                    "name": r[2],
                    "estimate_hours": r[3],
                    "dependencies": r[4].split(",") if r[4] else [],
                }
            )
        return out


def list_milestones(project_id: int) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, name, target_date FROM milestones WHERE project_id=?", (project_id,)
        )
        rows = cur.fetchall()
        return [
            {"id": r[0], "name": r[1], "target_date": r[2]}  # target_date as stored string
            for r in rows
        ]
