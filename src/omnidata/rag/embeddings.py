"""OpenAI embeddings (ADR 0009). Sync on purpose, like every other network call in bot/repo.py (psycopg's driver is sync
too) — the worker processes one message at a time, so there is no concurrency to lose by blocking for one HTTP call."""
from __future__ import annotations

from typing import Protocol

import httpx

DEFAULT_BASE_URL = "https://api.openai.com/v1"


class EmbeddingsError(RuntimeError):
    pass


class Embeddings(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class OpenAIEmbeddings:
    def __init__(self, api_key: str, model: str = "text-embedding-3-small", base_url: str = DEFAULT_BASE_URL,
                 transport: httpx.BaseTransport | None = None) -> None:
        self._model = model
        self._base = base_url.rstrip("/")
        self._http = httpx.Client(transport=transport, timeout=30.0, headers={"Authorization": f"Bearer {api_key}"})

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        r = self._http.post(f"{self._base}/embeddings", json={"model": self._model, "input": texts})
        if r.status_code != 200:
            raise EmbeddingsError(f"http {r.status_code}: {r.text[:200]}")
        data = r.json()["data"]
        return [row["embedding"] for row in sorted(data, key=lambda row: row["index"])]
