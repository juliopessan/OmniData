"""Glue between synth.py (Postgres, the source of truth) and the Chroma index (ADR 0009): embed each transcript's text and
upsert it with {transcript_id, hs_owner_id} metadata. Kept separate from synth.py so the DB-only part stays testable without
any network call."""
from __future__ import annotations

from typing import Any

from ..rag.chroma import VectorStore
from ..rag.embeddings import Embeddings


def index_transcripts(embeddings: Embeddings, store: VectorStore, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    vectors = embeddings.embed([r["text"] for r in rows])
    store.upsert(ids=[r["id"] for r in rows], embeddings=vectors,
                metadatas=[{"transcript_id": r["id"], "hs_owner_id": r["hs_owner_id"]} for r in rows])
    return len(rows)
