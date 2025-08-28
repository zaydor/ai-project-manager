# AI Project Manager Backend (Flask + Ollama)

Local-only agent API providing project intake, planning, scheduling preview, and an apply (integration) endpoint.

## Features

- Uses a local Ollama 7B model (default: `mistral:7b`) for clarifying question generation and lightweight planning assistance.
- SQLite persistence (projects, milestones, tasks, schedule).
- Dry-run safe integration stub for Todoist & Google Calendar (never writes unless `dry_run=false` AND `confirm=true`).
- Docker Compose setup with a colocated Ollama service.
- Uses `uv` for Python dependency resolution (fast, lock-free by default).

## Quick Start (Local Dev)

Prereqs: `ollama` installed locally (https://ollama.com/) and the model pulled.

```bash
# Pull a 7B model (choose one you prefer)
ollama pull mistral:7b

# (Optional) create a virtual env; uv can also run ad-hoc
uv sync  # installs dependencies from pyproject.toml

# Run Flask API (binds to 127.0.0.1 only by default)
uv run python main.py

# Test intake endpoint
curl -s -X POST http://127.0.0.1:5000/projects/intake -H 'Content-Type: application/json' \
  -d '{"summary":"Build a small habit tracker mobile app"}' | jq
```

## Docker Compose

```bash
docker compose up --build
```

Services:

- `backend`: Flask API
- `ollama`: Ollama server (exposes 11434 to backend only on internal network)

Inside the compose setup the backend targets the `ollama` host instead of localhost.

## Environment Variables (.env)

Create a `.env` (or override via compose) with:

```
AGENT_MODEL=mistral:7b
LOG_LEVEL=INFO
OLLAMA_HOST=http://ollama:11434  # overridden when running in compose

# Integration placeholders (only needed if you later enable real writes)
TODOIST_API_TOKEN=your_todoist_token_here
GOOGLE_SERVICE_ACCOUNT_JSON=/path/to/service_account.json
```

## Endpoints Summary

| Endpoint                     | Method | Purpose                                                              |
| ---------------------------- | ------ | -------------------------------------------------------------------- |
| `/projects/intake`           | POST   | Generate clarifying questions from a summary.                        |
| `/projects/plan`             | POST   | Turn answers into a lightweight plan (milestones, tasks, estimates). |
| `/projects/schedule_preview` | POST   | Produce an in-memory schedule preview based on availability.         |
| `/projects/apply`            | POST   | (Dry-run by default) simulate pushing tasks to Todoist / Calendar.   |

## Safety: Dry-Run Default

`/projects/apply` will ONLY perform external writes if BOTH `dry_run=false` and `confirm=true` are supplied. Otherwise it logs intended actions only.

## Integration Notes

This backend is a subcomponent of the broader `ai_project_manager` system. You can mount it behind a gateway or call it directly from a frontend/UI module.

## Simple Development Workflow

1. Modify prompts / logic in `ollama_client.py`.
2. Adjust DB schema or helper methods in `db.py` (auto-creates tables on startup).
3. Evolve Pydantic models in `models.py`.
4. Add richer planning logic in `main.py` where indicated by TODO comments.

## Tests (Optional Example)

You can add pytest tests under `tests/` and run:

```bash
uv run pytest -q
```

## Production Hardening (Future Work)

- Add auth (API keys / JWT) for endpoints.
- More robust parsing of LLM outputs (possible JSON mode or structured prompting).
- Replace naive scheduling with constraint solver.
- Implement actual Todoist / Google Calendar API interactions.

## License

MIT
