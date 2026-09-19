"""Degraded-mode keyword router (FR-BOT-7): serves the top intents with no LLM."""
from __future__ import annotations

import re
import unicodedata

_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("get_quota_status", re.compile(r"\b(meta|quota|atingimento|falta quanto|quanto falta)\b")),
    ("get_kpis", re.compile(r"\b(numeros?|kpis?|win ?rate|conversao|taxa de ganho|resultado)\b")),
    ("get_pipeline_summary", re.compile(r"\b(pipeline|funil|etapas?)\b")),
    ("list_deals_needing_action", re.compile(r"\b(acao|atencao|parados?|prioridades?|precisam|urgente|o que fazer)\b")),
    ("get_morning_brief", re.compile(r"\b(meu dia|resumo|bom dia|brief|hoje)\b")),
]


def _norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


def keyword_route(text: str) -> str | None:
    t = _norm(text)
    for tool, rx in _RULES:
        if rx.search(t):
            return tool
    return None
