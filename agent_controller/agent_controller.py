"""Agent controller utilities.

This module provides higher-level functions that orchestrate the backend Ollama client,
persistence into the project's SQLite database, and a small, pluggable embedding index
(with optional FAISS/Chroma support and a deterministic fallback).

Exports:
- generate_clarifying_questions(project_summary)
- generate_plan(answers)
- score_and_estimate(tasks)
- create_schedule(tasks, availability)

It also contains pure, unit-testable helpers for partitioning and scheduling.

Prompt templates used with Ollama are included below as SAMPLE_PROMPT_* constants.

Notes / assumptions:
- This module prefers the `backend` package's `ollama_client` and `db` helpers.
- If FAISS or Chroma are not installed, a deterministic hashed-embedding fallback is
  used so the module remains runnable with no extra native deps.
- Embeddings are persisted into a simple `embeddings` table created on demand in the
  same SQLite `app.db` used by `backend.db`.

"""

from __future__ import annotations

import importlib.util
import json
import logging
import sqlite3
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Local project imports
try:
    from backend import db as backend_db
    from backend.models import MilestoneModel, TaskModel
    from backend.ollama_client import OllamaClient
except Exception:  # pragma: no cover - import errors in some test envs
    # Provide light fallback stubs for typing / lints when running tests outside
    # the repo
    OllamaClient = None  # type: ignore
    backend_db = None  # type: ignore
    TaskModel = object  # type: ignore
    MilestoneModel = object  # type: ignore

logger = logging.getLogger(__name__)

# SAMPLE PROMPT TEMPLATES
SAMPLE_PROMPT_CLARIFY = (
    "You are a concise project analyst. Given the project summary below, "
    "generate exactly 5 short clarifying questions in JSON under the key 'questions'. "
    "Return strictly valid JSON.\n\nProject summary:\n{summary}\n\nJSON:"
)

SAMPLE_PROMPT_PLAN = (
    "You are a pragmatic project planner. Given the project summary and the user's "
    "answers to clarifying questions, return a JSON object with two keys: 'milestones' "
    "(list of {{title, description, estimate_hours}}) and 'tasks' "
    "(list of {title, description, estimate_hours, milestone_index}). "
    "Return strictly valid JSON.\n\nContext: {context}\n\nJSON:"
)

SAMPLE_PROMPT_SCORE_ESTIMATE = (
    "You are a senior engineer estimating effort and risk. Given a task title and "
    "description, return JSON {{'estimate_hours': <number>, 'confidence': <0-1 float>, "
    "'notes': '...'}}. Return strictly valid JSON.\n\nTask: {task}\nJSON:"
)

# Embedding / vector index helpers. Try faiss/chroma if available; otherwise use
# deterministic hashing fallback.
_HAS_FAISS = importlib.util.find_spec("faiss") is not None
_HAS_CHROMA = importlib.util.find_spec("chromadb") is not None
_HAS_SBT = importlib.util.find_spec("sentence_transformers") is not None


class SimpleEmbeddingIndex:
    """A tiny deterministic embedding index with optional faiss/chroma backends.

    The implementation aims to be lightweight and safe for unit tests.
    If neither FAISS nor Chroma are present, it falls back to an in-memory
    list of vectors built from a sha256-based deterministic float conversion.
    """

    def __init__(self):
        self._use_faiss = _HAS_FAISS
        self._use_chroma = _HAS_CHROMA and not self._use_faiss
        self._items: List[Dict[str, Any]] = []
        self._id_counter = 1

        # If sentence-transformers available, use it for higher-quality embeddings
        if _HAS_SBT:
            # note: model load may be slow; kept optional.
            # Import lazily to avoid top-level import.
            try:
                from sentence_transformers import SentenceTransformer  # type: ignore

                self._embedder = SentenceTransformer("all-MiniLM-L6-v2")
            except Exception:
                self._embedder = None
        else:
            self._embedder = None

    def _deterministic_vector(self, text: str, dim: int = 8) -> List[float]:
        """Map text deterministically to a float vector using sha256.

        This is intentionally deterministic so unit tests can rely on stable outputs.
        """
        digest = sha256(text.encode("utf-8")).digest()
        # turn into dim floats in [0,1)
        vals = []
        for i in range(dim):
            chunk = digest[i * 4 : (i + 1) * 4]
            v = int.from_bytes(chunk, "big") / 2**32
            vals.append(float(v))
        return vals

    def embed_texts(self, texts: Sequence[str]) -> List[List[float]]:
        if self._embedder:
            vecs = self._embedder.encode(list(texts), show_progress_bar=False)
            return [list(map(float, v)) for v in vecs]
        else:
            return [self._deterministic_vector(t) for t in texts]

    def add(
        self, texts: Sequence[str], metadatas: Optional[Sequence[Dict[str, Any]]] = None
    ) -> List[int]:
        vecs = self.embed_texts(list(texts))
        ids: List[int] = []
        for i, v in enumerate(vecs):
            item = {
                "id": self._id_counter,
                "text": texts[i],
                "vector": v,
                "metadata": (metadatas[i] if metadatas else {}),
            }
            self._items.append(item)
            ids.append(self._id_counter)
            self._id_counter += 1
        return ids

    def query(
        self, query_text: str, top_k: int = 5
    ) -> List[Tuple[int, float, Dict[str, Any]]]:
        qv = self.embed_texts([query_text])[0]
        results: List[Tuple[int, float, Dict[str, Any]]] = []
        for it in self._items:
            # cosine similarity approx using dot/(norms)
            dot = sum(a * b for a, b in zip(qv, it["vector"], strict=False))
            # compute norms
            qa = sum(a * a for a in qv) ** 0.5
            ib = sum(b * b for b in it["vector"]) ** 0.5
            sim = dot / (qa * ib + 1e-12)
            results.append((it["id"], sim, it["metadata"]))
        results.sort(key=lambda r: r[1], reverse=True)
        return results[:top_k]


# Embeddings persistence
def ensure_embeddings_table(conn: sqlite3.Connection):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS embeddings (
            id INTEGER PRIMARY KEY,
            project_id INTEGER,
            item_id INTEGER,
            text TEXT,
            vector TEXT,
            metadata TEXT
        )
        """
    )


def persist_embeddings(
    conn: sqlite3.Connection,
    project_id: int,
    ids: Sequence[int],
    texts: Sequence[str],
    vectors: Sequence[Sequence[float]],
    metadatas: Optional[Sequence[Dict[str, Any]]] = None,
):
    ensure_embeddings_table(conn)
    cur = conn.cursor()
    for idx, text, vec in zip(ids, texts, vectors, strict=False):
        cur.execute(
            "INSERT INTO embeddings(id, project_id, item_id, text, vector, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                None,
                project_id,
                idx,
                text,
                json.dumps(vec),
                json.dumps(metadatas or {}),
            ),
        )
    conn.commit()


# Controller functions


def generate_clarifying_questions(
    project_summary: str, persist: bool = True
) -> Dict[str, Any]:
    """Generate clarifying questions for a project.

    Returns dict {project_id, questions} where questions is a list of strings.
    If persist=True, the project summary and clarifying questions are inserted
    into the backend DB.
    """
    client = OllamaClient()
    prompt = SAMPLE_PROMPT_CLARIFY.format(summary=project_summary)
    raw = client.ask_json(
        prompt, expected_schema_hint="{ 'questions': ['q1','q2','q3','q4','q5'] }"
    )
    questions = raw.get("questions") or raw.get("data") or raw
    if isinstance(questions, dict):
        questions = [v for v in questions.values() if isinstance(v, str)]
    if not isinstance(questions, list):
        # deterministic fallback
        questions = [
            "What are the primary technical goals?",
            "Who are the main users?",
            "What is the desired deadline?",
            "Are there stack constraints or preferences?",
            "Any non-functional requirements (scaling, latency)?",
        ]

    project_id = None
    if persist and backend_db:
        try:
            project_id = backend_db.insert_project(
                project_summary, json.dumps(questions)
            )
        except Exception as e:
            logger.exception("Failed to persist project: %s", e)

    return {"project_id": project_id, "questions": questions}


def generate_plan(
    project_id: int, answers: Dict[str, Any], persist: bool = True
) -> Dict[str, Any]:
    """Generate milestones and tasks given answers mapping.

    Persist to DB if persist=True.
    Returns dict with milestones and tasks as native dicts.
    """
    client = OllamaClient()
    # load context from DB if available
    summary = ""
    if backend_db:
        proj = backend_db.get_project(project_id)
        if proj:
            summary = proj.get("summary", "")
    context = {"summary": summary, "answers": answers}
    prompt = SAMPLE_PROMPT_PLAN.format(context=json.dumps(context))
    raw = client.ask_json(
        prompt, expected_schema_hint="{ 'milestones': [...], 'tasks': [...] }"
    )
    milestones_raw = raw.get("milestones", [])
    tasks_raw = raw.get("tasks", [])

    milestones = [
        {
            "title": m.get("title"),
            "description": m.get("description"),
            "estimate_hours": m.get("estimate_hours"),
        }
        for m in milestones_raw
    ]
    tasks = []
    for t in tasks_raw:
        tasks.append(
            {
                "title": t.get("title"),
                "description": t.get("description"),
                "estimate_hours": t.get("estimate_hours"),
                "milestone_index": t.get("milestone_index"),
            }
        )

    if persist and backend_db:
        try:
            backend_db.insert_milestones(project_id, milestones)
            backend_db.insert_tasks(project_id, tasks)
        except Exception:
            logger.exception("Failed to persist milestones/tasks")

    return {"project_id": project_id, "milestones": milestones, "tasks": tasks}


def score_and_estimate(tasks: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Score tasks for priority/risk and produce/adjust hour estimates.

    Uses Ollama to get deterministic JSON outputs; falls back to a simple heuristic.
    Returns a list of task dicts with added keys: estimate_hours, confidence.
    """
    client = OllamaClient()
    out: List[Dict[str, Any]] = []
    for t in tasks:
        # Construct a concise prompt per task
        task_desc = f"Title: {t.get('title')}\nDescription: {t.get('description', '')}"
        prompt = SAMPLE_PROMPT_SCORE_ESTIMATE.format(task=task_desc)
        res = client.ask_json(
            prompt, expected_schema_hint="{ 'estimate_hours': 1.0, 'confidence': 0.8 }"
        )
        if isinstance(res, dict) and "estimate_hours" in res:
            est = float(res.get("estimate_hours") or 1.0)
            conf = float(res.get("confidence") or 0.5)
        else:
            # heuristic: 1 hour per 100 chars of title+desc, min 0.5h
            text_len = len((t.get("title", "") + "\n" + (t.get("description") or "")))
            est = max(0.5, round(text_len / 100.0 * 2.0, 2))
            conf = 0.4
        newt = dict(t)
        newt["estimate_hours"] = est
        newt["confidence"] = conf
        out.append(newt)
    return out


# Pure, unit-testable helpers


def partition_tasks_greedy(
    tasks: Sequence[Dict[str, Any]], max_hours: float
) -> List[List[Dict[str, Any]]]:
    """Greedy partition tasks into groups where sum(estimate_hours) <= max_hours.

    Deterministic and pure: does not touch I/O.
    Tasks without estimate_hours are treated as 1.0.
    """
    groups: List[List[Dict[str, Any]]] = []
    current: List[Dict[str, Any]] = []
    current_sum = 0.0
    for t in tasks:
        est = float(t.get("estimate_hours") or 1.0)
        if current and current_sum + est > max_hours:
            groups.append(current)
            current = [t]
            current_sum = est
        else:
            current.append(t)
            current_sum += est
    if current:
        groups.append(current)
    return groups


def schedule_sequential(
    tasks: Sequence[Dict[str, Any]],
    hours_per_day: float,
    start_dt: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Create a naive sequential schedule for tasks.

    Pure and deterministic. Returns list of dicts: {task_id, start_ts, end_ts}
    with ISO timestamps.
    """
    if start_dt is None:
        start_dt = datetime.utcnow().replace(hour=9, minute=0, second=0, microsecond=0)
    cursor = start_dt
    schedule: List[Dict[str, Any]] = []
    for t in tasks:
        est = float(t.get("estimate_hours") or 1.0)
        days = est / hours_per_day
        # represent days as fractional days; end time is cursor + days
        delta = timedelta(days=days)
        end = cursor + delta
        schedule.append(
            {
                "task_id": t.get("id"),
                "start_ts": cursor.isoformat(),
                "end_ts": end.isoformat(),
            }
        )
        cursor = end
    return schedule


def create_schedule(
    tasks: Sequence[Dict[str, Any]], availability: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """High-level schedule creation.

    availability: { 'hours_per_day': float }
    Uses the pure schedule_sequential helper; also persists schedule to DB if
    backend_db present.
    """
    hours = float(availability.get("hours_per_day", 4))
    sched = schedule_sequential(tasks, hours_per_day=hours)
    # persist
    if backend_db:
        try:
            backend_db.insert_schedule(
                tasks[0].get("project_id")
                if tasks and tasks[0].get("project_id")
                else 0,
                sched,
            )
        except Exception:
            logger.exception("Failed to persist schedule")
    return sched


# Convenience: create an index, persist embeddings for a project's tasks
def index_project_tasks(
    project_id: int,
    tasks: Sequence[Dict[str, Any]],
    index: Optional[SimpleEmbeddingIndex] = None,
):
    """
    Embed task titles+descriptions, add to index and persist vectors to SQLite
    embeddings table.

    Returns the internal ids assigned by the index.
    """
    idx = index or SimpleEmbeddingIndex()
    texts = [f"{t.get('title', '')}\n{t.get('description', '') or ''}" for t in tasks]
    ids = idx.add(texts, metadatas=[{"task": t.get("title")} for t in tasks])
    vectors = idx.embed_texts(texts)  # deterministic
    # persist to DB
    try:
        if backend_db:
            with backend_db.get_conn() as conn:
                persist_embeddings(
                    conn,
                    project_id,
                    ids,
                    texts,
                    vectors,
                    metadatas=[{"task": t.get("title")} for t in tasks],
                )
    except Exception:
        logger.exception("Failed to persist embeddings")
    return ids


# Expose a small API surface for importable use
__all__ = [
    "generate_clarifying_questions",
    "generate_plan",
    "score_and_estimate",
    "create_schedule",
    "partition_tasks_greedy",
    "schedule_sequential",
    "SimpleEmbeddingIndex",
    "index_project_tasks",
]
