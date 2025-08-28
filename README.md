
# AI Project Manager

[![CI](https://github.com/zaydor/ai-project-manager/actions/workflows/ci.yml/badge.svg)](https://github.com/zaydor/ai-project-manager/actions/workflows/ci.yml)
[![Lint](https://github.com/zaydor/ai-project-manager/actions/workflows/lint.yml/badge.svg)](https://github.com/zaydor/ai-project-manager/actions/workflows/lint.yml)
[![Docker Build](https://github.com/zaydor/ai-project-manager/actions/workflows/docker-build.yml/badge.svg)](https://github.com/zaydor/ai-project-manager/actions/workflows/docker-build.yml)

This repo contains a local-only Flask backend that uses Ollama for LLM-powered project intake, planning, and scheduling. The backend is in `backend/` and has dry-run-safe connectors for Todoist and Google Calendar.

## Local development

1. Install Ollama and pull a model (recommended 7B):

```bash
# install ollama: https://ollama.com/
ollama pull phi3:mini
```

2. Create a virtual environment and install dependencies. Recommended: `uv` (as used in project)

```bash
uv sync
uv run python -m pip install -r requirements.txt  # optional if you prefer pip
```

3. Run the backend (binds to localhost only):

```bash
uv run python backend/main.py
```

4. Use the included Postman/Insomnia collection (`postman_collection.json`) to test endpoints.

## How to run Ollama (local)

- Start the Ollama daemon on your machine. By default it listens on port 11434.
- Pull a model: `ollama pull <model>` (e.g. `phi3:mini`, `mistral:7b`, or any 7B model you prefer).
- Validate the endpoint: `curl http://localhost:11434/v1/models` should list available models.

If you run via Docker Compose in `backend/docker-compose.yml`, the backend will resolve the `ollama` hostname to the Ollama service inside the compose network.

## Troubleshooting

- If Flask fails to start: ensure `python` in your PATH matches the interpreter used to install packages; run `uv run python backend/main.py` to use the project venv.
- Ollama connection errors: verify Ollama daemon is running and the model is pulled. Check `OLLAMA_HOST` env var in `backend/.env.example`.
- Tests failing: run `.venv/bin/python -m pytest -q` to use the venv-installed pytest. If `pip` is missing in the venv, run `.venv/bin/python -m ensurepip --upgrade` then install pytest.
- External writes: endpoints respect `dry_run` and `confirm` flags. `/projects/apply` will NOT write to Todoist/Calendar unless `dry_run=false` AND `confirm=true`.

## Postman / Insomnia

Use `postman_collection.json` to import a sample collection for the main endpoints.

## Next steps

- Add CI (GitHub Actions) to run tests and linting on push.
- Add integration tests for connectors using VCR or recorded fixtures.
