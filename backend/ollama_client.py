from __future__ import annotations

import json
import logging
import os
from typing import List
import httpx

logger = logging.getLogger(__name__)


class OllamaClient:
    """Minimal wrapper for Ollama /api/generate endpoint.

    Assumes the Ollama server is reachable at OLLAMA_HOST (default http://localhost:11434).
    """

    def __init__(self, model: str | None = None, host: str | None = None, timeout: float = 60.0):
        self.model = model or os.getenv("AGENT_MODEL", "mistral:7b")
        self.host = host or os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.timeout = timeout
        self._client = httpx.Client(timeout=timeout)

    def generate(self, prompt: str, system: str | None = None) -> str:
        url = f"{self.host.rstrip('/')}/api/generate"
        payload = {"model": self.model, "prompt": prompt, "stream": False}
        if system:
            payload["system"] = system
        logger.debug("Ollama request: %s", payload)
        try:
            resp = self._client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", "").strip()
        except httpx.HTTPError as e:
            logger.exception("Ollama request failed")
            raise RuntimeError(f"Ollama request failed: {e}") from e

    # --- Higher-level helpers -------------------------------------------------
    def clarifying_questions(self, summary: str, max_q: int = 5) -> List[str]:
        system = (
            "You are an expert project analyst. Produce concise clarifying questions to better define "
            "a software project. Return bullet list, each question one line."
        )
        prompt = f"Project summary:\n{summary}\n\nQuestions:"
        raw = self.generate(prompt, system=system)
        questions: List[str] = []
        for line in raw.splitlines():
            line = line.strip(" -\t")
            if not line:
                continue
            if len(questions) >= max_q:
                break
            # Basic heuristic to end on sentence end
            questions.append(line.rstrip("?") + "?")
        if not questions:
            questions = ["What is the primary goal?", "Who are the end users?"]
        return questions

    def draft_plan(self, summary: str, answers: dict) -> dict:
        system = "You are a helpful project planner. Provide JSON with milestones and tasks."  # simple
        # Provide a very constrained instruction hoping for JSON-like output.
        prompt = (
            "SUMMARY:"\
            f" {summary}\nANSWERS: {json.dumps(answers)}\n"\
            "Return JSON with keys milestones (list of names) and tasks (list of {name, milestone, estimate_hours})."
        )
        raw = self.generate(prompt, system=system)
        # Naive JSON extraction
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            snippet = raw[start : end + 1]
            try:
                parsed = json.loads(snippet)
                return parsed
            except json.JSONDecodeError:
                logger.warning("Failed to parse plan JSON. Raw: %s", raw)
        # fallback minimal plan
        return {
            "milestones": ["Draft", "Build", "Review"],
            "tasks": [
                {"name": "Draft spec", "milestone": "Draft", "estimate_hours": 2},
                {"name": "Implement core", "milestone": "Build", "estimate_hours": 8},
                {"name": "Review & refine", "milestone": "Review", "estimate_hours": 3},
            ],
        }
