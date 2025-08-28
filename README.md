# AI Project Manager

[![CI](https://github.com/zaydor/ai-project-manager/actions/workflows/ci.yml/badge.svg)](https://github.com/zaydor/ai-project-manager/actions/workflows/ci.yml)
[![Lint](https://github.com/zaydor/ai-project-manager/actions/workflows/lint.yml/badge.svg)](https://github.com/zaydor/ai-project-manager/actions/workflows/lint.yml)
[![Docker Build](https://github.com/zaydor/ai-project-manager/actions/workflows/docker-build.yml/badge.svg)](https://github.com/zaydor/ai-project-manager/actions/workflows/docker-build.yml)

A local-first, LLM-powered project intake, planning, and scheduling backend with dry-run-safe integrations for Todoist and Google Calendar. Powered by Flask, SQLite, and Ollama (local LLMs).

---

## Features

- **LLM-powered project intake:** Uses a local Ollama model (default: `mistral:7b`) to generate clarifying questions and assist with project planning.
- **Planning & scheduling:** Converts user answers into milestones, tasks, and a schedule preview based on your availability.
- **Dry-run safe integrations:** Simulates (or actually performs) pushes to Todoist and Google Calendar, with strict `dry_run` and `confirm` flags for safety.
- **SQLite persistence:** Projects, milestones, tasks, and schedules are stored locally.
- **Modern Python tooling:** Uses `uv` for fast dependency management and reproducible environments.
- **Docker & Compose:** Easy local or containerized setup, with Ollama and backend services.

---

## Quick Start

### 1. Prerequisites

- [Ollama](https://ollama.com/) installed locally (for LLM inference)
- Python 3.11+ (recommended: 3.13)
- [uv](https://github.com/astral-sh/uv) (for dependency management)

### 2. Pull a model for Ollama

```bash
ollama pull mistral:7b
# or: ollama pull phi3:mini
```

### 3. Install dependencies

```bash
uv sync
```

### 4. Run the backend

```bash
uv run python backend/main.py
# or, for direct Python: python -m backend.main
```

The API will be available at `http://127.0.0.1:5000`.

---

## Docker & Docker Compose

To run the backend and Ollama together:

```bash
cd backend
docker compose up --build
```

- The backend will connect to the Ollama service at `http://ollama:11434`.
- See `backend/docker-compose.yml` for service details.

---

## Environment Variables

Copy `backend/.env.example` to `.env` and adjust as needed:

```
AGENT_MODEL=mistral:7b
LOG_LEVEL=INFO
OLLAMA_HOST=http://localhost:11434
TODOIST_API_TOKEN=your_todoist_token_here
GOOGLE_SERVICE_ACCOUNT_JSON=/path/to/service_account.json
```

---

## API Endpoints

| Endpoint                     | Method | Purpose                                                              |
|------------------------------|--------|----------------------------------------------------------------------|
| `/projects/intake`           | POST   | Generate clarifying questions from a summary.                        |
| `/projects/plan`             | POST   | Turn answers into a lightweight plan (milestones, tasks, estimates). |
| `/projects/schedule_preview` | POST   | Produce an in-memory schedule preview based on availability.         |
| `/projects/apply`            | POST   | (Dry-run by default) simulate or perform pushes to Todoist/Calendar. |

- See `postman_collection.json` for ready-to-use API requests.

---

## Safety: Dry-Run by Default

The `/projects/apply` endpoint will **only** perform external writes if both `dry_run=false` and `confirm=true` are set. Otherwise, it logs intended actions only.

---

## Testing

Run all tests with:

```bash
uv run pytest -q
```

---

## Troubleshooting

- **Flask fails to start:** Ensure you’re using the correct Python interpreter and dependencies are installed (`uv run python backend/main.py`).
- **Ollama connection errors:** Make sure the Ollama daemon is running and the model is pulled. Check the `OLLAMA_HOST` variable.
- **Tests failing:** Use the project venv (`.venv/bin/python -m pytest -q`). If `pip` is missing, run `.venv/bin/python -m ensurepip --upgrade` then install pytest.
- **External writes:** Endpoints respect `dry_run` and `confirm` flags. No real integration occurs unless both are set.

---

## Contributing

- Lint with `ruff check .`
- Add tests in `tests/`
- See GitHub Actions for CI status

---

## License

MIT

---
