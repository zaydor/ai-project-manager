"""Google Calendar client helpers with dry-run default.

Provides:
- make_event_objects(schedule) -> list of event dicts
- dry_run_create_events(events) -> preview summary
- apply_create_events(
    credentials, events, dry_run=True
  ) -> create events, return created event ids

Uses google-api-python-client when available; otherwise functions still work in dry-run
mode and raise a RuntimeError if apply_create_events is called with dry_run=False and no
libraries.

Includes retry/backoff for transient errors and notes on configuring GCP OAuth client.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Any, Dict, Iterable, List

logger = logging.getLogger(__name__)

try:
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError

    _HAS_GOOGLEAPI = True
except Exception:  # pragma: no cover - optional deps
    build = None  # type: ignore
    HttpError = Exception  # type: ignore
    _HAS_GOOGLEAPI = False


def make_event_objects(schedule: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Turn schedule rows into Google Calendar event objects.

    Schedule rows expected to have: task_id, start_ts (ISO), end_ts (ISO), title,
    description.
    Returns list of dicts matching the Google Calendar API event resource format.
    """
    events: List[Dict[str, Any]] = []
    for s in schedule:
        ev = {
            "summary": s.get("title") or f"Task {s.get('task_id')}",
            "description": s.get("description") or s.get("notes"),
            "start": {
                "dateTime": s.get("start_ts"),
                "timeZone": s.get("time_zone", "UTC"),
            },
            "end": {"dateTime": s.get("end_ts"), "timeZone": s.get("time_zone", "UTC")},
        }
        events.append(ev)
    return events


def dry_run_create_events(events: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Return a preview of events that would be created. No network calls."""
    ev = list(events)
    logger.info("Dry run create events: %s events", len(ev))
    return {"count": len(ev), "sample": ev[:5]}


def _request_with_retry(
    func, *args, max_retries: int = 5, backoff_base: float = 0.5, **kwargs
):
    attempt = 0
    while attempt < max_retries:
        try:
            return True, func(*args, **kwargs)
        except HttpError as e:
            logger.warning("Calendar API HttpError (attempt %s): %s", attempt + 1, e)
            # naive backoff
            time.sleep(backoff_base * (2**attempt) + random.random() * 0.1)
            attempt += 1
            continue
        except Exception as e:
            logger.exception("Unexpected error calling Google API: %s", e)
            return False, e
    return False, {"error": "max_retries_exceeded"}


def apply_create_events(
    credentials: Any,
    events: Iterable[Dict[str, Any]],
    calendar_id: str = "primary",
    dry_run: bool = True,
) -> List[Dict[str, Any]]:
    """Create events on Google Calendar.

    - credentials: google oauth2 credentials object (from
      oauth_helper.load_credentials/run_local_oauth_flow)
    - events: iterable of event dicts from make_event_objects
    - calendar_id: calendar to add events to (default 'primary')
    - dry_run: if True, do not perform network calls and return a preview.

    Returns list of dicts: {success: bool, response_or_error}

    Notes on Google Cloud Console config:
    - Create OAuth 2.0 Client ID (Desktop or Web). For a web client, add redirect URI http://localhost:PORT/
    - Enable Google Calendar API for the project.
    - Download client_secret.json and use
      `helpers.oauth_helper.run_local_oauth_flow` to obtain credentials.
    """
    ev = list(events)
    if dry_run:
        return [{"success": False, "reason": "dry_run", "event": e} for e in ev]

    if not _HAS_GOOGLEAPI or credentials is None:
        raise RuntimeError(
            "google-api-python-client is required to create events. "
            "Install google-api-python-client and oauth libraries."
        )

    service = build("calendar", "v3", credentials=credentials)
    results: List[Dict[str, Any]] = []
    for e in ev:

        def _insert(e=e):
            return service.events().insert(calendarId=calendar_id, body=e).execute()

        ok, resp = _request_with_retry(_insert)
        if ok:
            results.append({"success": True, "response": resp})
        else:
            results.append({"success": False, "response": resp})
    return results
