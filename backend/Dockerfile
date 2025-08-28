FROM python:3.11-slim

# Install uv (fast Python package installer)
RUN pip install --no-cache-dir uv
WORKDIR /app

COPY pyproject.toml README.md ./
RUN uv sync --frozen --no-cache

COPY . .

ENV HOST=0.0.0.0 \
    PORT=5000 \
    LOG_LEVEL=INFO \
    OLLAMA_HOST=http://ollama:11434 \
    AGENT_MODEL=mistral:7b

EXPOSE 5000

CMD ["uv", "run", "python", "main.py"]
