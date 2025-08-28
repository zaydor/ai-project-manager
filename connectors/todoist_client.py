"""Todoist client helpers (dry-run safe).

Provides helpers to build Todoist task payloads from schedules and to create/delete
Todoist tasks with robust retry/backoff and rate-limit handling.

Functions:
- create_todoist_payloads(schedule) -> list[dict]
- dry_run_create(payloads) -> dict (summary)
- apply_create(token, payloads, dry_run=True) -> list of created task ids
- undo_created(token, created_ids) -> list of deletion results

Notes:
- This module never writes anywhere unless `apply_create` is called with `dry_run=False`
  and a valid token.
- All network calls use the REST v2 API (https://developer.todoist.com/rest/v2/).

Example usage:

>>> payloads = create_todoist_payloads([
...     {
...         "task_id": 1,
...         "start_ts": "2025-01-01T09:00:00Z",
...         "end_ts": "2025-01-01T10:00:00Z",
...         "title": "Do X"
...     }
... ])
>>> summary = dry_run_create(payloads)
>>> created = apply_create(
...     "TODOIST_TOKEN", payloads, dry_run=True
... )  # dry-run, will not call API
>>> created = apply_create("TODOIST_TOKEN", payloads, dry_run=False)  # actually create
>>> undo_created("TODOIST_TOKEN", created)
"""

from __future__ import annotations

import logging
import random
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)
TODOIST_TASKS_URL = "https://api.todoist.com/rest/v2/tasks"


def create_todoist_payloads(schedule: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert schedule items into Todoist /tasks payloads.

    schedule is an iterable of dicts with at least keys:
      - task_id (int)
      - start_ts (ISO string) or due date/time
      - end_ts (ISO string) optional
      - title (optional) string
      - description (optional) string

    Returns a list of payload dicts suitable for POST /tasks.

    The payload uses `due` with `date_time` when a start timestamp is present.
    The `content` field is the task title (fallbacked if absent).
    """
    out: List[Dict[str, Any]] = []
    for item in schedule:
        title = (
            item.get("title")
            or item.get("content")
            or f"Task {item.get('task_id') or ''}".strip()
        )
        desc = item.get("description") or item.get("notes")
        start = item.get("start_ts")
        due = None
        if start:
            due = {
                "date": start.split("T")[0],
                "date_time": start,
                "time_zone": "UTC",
            }
        # Todoist supports due as either {"date": "2020-01-01"} or date_time
        payload: Dict[str, Any] = {"content": title}
        if desc:
            payload["description"] = desc
        if due:
            payload["due"] = due
        # optional metadata for undo mapping
        payload["_meta"] = {"task_id": item.get("task_id")}
        out.append(payload)
    return out


def dry_run_create(payloads: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Return a dry-run summary of payloads that would be sent to Todoist.

    Does not perform any network calls. Returns a dict with counts and examples.
    """
    pl = list(payloads)
    summary = {
        "count": len(pl),
        "sample": pl[:5],
    }
    logger.info("Dry run create: %s tasks", len(pl))
    return summary


def _request_with_retry(
    method: str,
    url: str,
    headers: Dict[str, str],
    json_payload: Optional[Dict[str, Any]] = None,
    max_retries: int = 5,
    backoff_base: float = 0.5,
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """Internal helper: perform HTTP request with retry/backoff and rate-limit handling.

    Returns (success, response_json_or_none).
    """
    attempt = 0
    while attempt < max_retries:
        try:
            resp = requests.request(
                method, url, headers=headers, json=json_payload, timeout=15
            )
        except Exception as e:
            logger.warning("HTTP request exception (attempt %s): %s", attempt + 1, e)
            # transient network error -> retry
            attempt += 1
            sleep_for = backoff_base * (2**attempt) + random.random() * 0.1
            time.sleep(sleep_for)
            continue

        if resp.status_code in (200, 201, 204):
            if resp.status_code == 204:
                return True, None
            try:
                return True, resp.json()
            except Exception:
                return True, None
        elif resp.status_code == 429:
            # Rate limited. Check Retry-After
            retry_after = resp.headers.get("Retry-After")
            try:
                wait = (
                    float(retry_after) if retry_after else (backoff_base * (2**attempt))
                )
            except Exception:
                wait = backoff_base * (2**attempt)
            logger.warning(
                "Rate limited by Todoist (429). Sleeping for %s seconds (attempt %s)",
                wait,
                attempt + 1,
            )
            time.sleep(wait)
            attempt += 1
            continue
        elif 500 <= resp.status_code < 600:
            # server error, retry
            logger.warning(
                "Server error %s from Todoist, attempt %s",
                resp.status_code,
                attempt + 1,
            )
            attempt += 1
            time.sleep(backoff_base * (2**attempt) + random.random() * 0.1)
            continue
        else:
            # client error - do not retry
            try:
                err = resp.json()
            except Exception:
                err = {"status_code": resp.status_code, "text": resp.text}
            logger.error("Request failed %s: %s", resp.status_code, err)
            return False, err
    return False, {"error": "max_retries_exceeded"}


def apply_create(
    token: str, payloads: Iterable[Dict[str, Any]], dry_run: bool = True
) -> List[Dict[str, Any]]:
    """Create tasks in Todoist from prepared payloads.

    By default (dry_run=True) this function will NOT call the Todoist API and will
    instead return a summary of what would be created. To execute writes, pass
    dry_run=False and a valid token.

    Returns a list of dicts for each payload with keys:
      - success (bool)
      - response (dict or None)
      - payload (the original payload)

    Example:
        payloads = create_todoist_payloads(schedule)
        # preview
        apply_create("TOKEN", payloads, dry_run=True)
        # perform
        results = apply_create("TOKEN", payloads, dry_run=False)

    """
    pl = list(payloads)
    if dry_run:
        logger.info("apply_create called in dry-run mode: %s payloads", len(pl))
        return [{"success": False, "reason": "dry_run", "payload": p} for p in pl]

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    results: List[Dict[str, Any]] = []
    for p in pl:
        ok, resp = _request_with_retry(
            "POST", TODOIST_TASKS_URL, headers, json_payload=p
        )
        if ok:
            results.append({"success": True, "response": resp, "payload": p})
        else:
            results.append({"success": False, "response": resp, "payload": p})
    return results


def undo_created(
    token: str, created_results: Iterable[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Delete tasks that were created.

    Accepts an iterable of created result dicts as returned by `apply_create`
    (successful entries must contain `response` with an `id`).
    Returns a list of deletion results: {id, success, response_or_error}.

    This function will attempt to delete items with retries and log failures.
    """
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    out: List[Dict[str, Any]] = []
    for r in created_results:
        resp = r.get("response") or {}
        task_id = resp.get("id") if isinstance(resp, dict) else None
        if not task_id:
            out.append(
                {"id": None, "success": False, "error": "no id in response", "orig": r}
            )
            continue
        url = f"{TODOIST_TASKS_URL}/{task_id}"
        ok, del_resp = _request_with_retry("DELETE", url, headers, json_payload=None)
        out.append({"id": task_id, "success": ok, "response": del_resp})
    return out
