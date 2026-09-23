"""Thin wrapper over the Chroma client (ADR 0009). Chroma is a semantic INDEX only, never a permission boundary — it stores
just the embedding plus {transcript_id, hs_owner_id} as a coarse pre-filter. The caller (bot/repo.py::search_meetings) always
re-checks every match against Postgres via Principal.owner_clause() before returning anything; a leak here is not the last
line of defense. Sync client, same reasoning as rag/embeddings.py."""
from __future__ import annotations

from typing import Any, Protocol


class VectorStore(Protocol):
    def upsert(self, ids: list[str], embeddings: list[list[float]], metadatas: list[dict[str, Any]]) -> None: ...
    def query(self, embedding: list[float], limit: int, where: dict[str, Any] | None = None) -> list[tuple[str, float]]: ...


class ChromaStore:
    def __init__(self, url: str, collection: str) -> None:
        from urllib.parse import urlparse

        import chromadb
        u = urlparse(url)
        self._client = chromadb.HttpClient(host=u.hostname or "localhost", port=u.port or 8000)
        self._collection_name = collection

    def _collection(self) -> Any:
        return self._client.get_or_create_collection(self._collection_name)

    def upsert(self, ids: list[str], embeddings: list[list[float]], metadatas: list[dict[str, Any]]) -> None:
        self._collection().upsert(ids=ids, embeddings=embeddings, metadatas=metadatas)

    def query(self, embedding: list[float], limit: int, where: dict[str, Any] | None = None) -> list[tuple[str, float]]:
        res = self._collection().query(query_embeddings=[embedding], n_results=limit, where=where)
        ids, dists = (res.get("ids") or [[]])[0], (res.get("distances") or [[]])[0]
        return list(zip(ids, dists, strict=True))
