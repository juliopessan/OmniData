"""Degraded-mode keyword router (FR-BOT-7): serves the top intents with no LLM."""
from __future__ import annotations

import re
import unicodedata

_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("get_fix_queue", re.compile(r"\b(corrigir|correcao|correcoes|preencher|arrumar|higiene|fila de correcao|o que (esta )?faltando|dados faltando)\b")),
    ("get_insight_digest", re.compile(r"\b(insight do dia|insight de hoje|destaque do dia)\b")),
    ("get_insight_coverage", re.compile(r"\b(cobertura|confiar nos insights?|insights? confiaveis?)\b")),
    ("get_pains", re.compile(r"\b(dores?|dificuldades? das empresas|problemas? das empresas)\b")),
    ("get_recurring_terms", re.compile(r"\b(termos?|palavras?|frases?|recorrentes?|se repete|se repetem)\b")),
    ("get_demand_types", re.compile(r"\b(demandas?|o que (as )?empresas (compram|pedem|buscam))\b")),
    ("get_systems_landscape", re.compile(r"\b(erps?|sistemas?|totvs|concorrentes?)\b")),
    ("get_segment_insights", re.compile(r"\b(segmentos?|campanhas?|nichos?|motivos? de perda|por que perd\w+)\b")),
    ("get_quota_status", re.compile(r"\b(meta|quota|atingimento|falta quanto|quanto falta)\b")),
    ("get_data_quality", re.compile(r"\b(qualidade|confiavel|confiar|meus dados|amostra)\b")),
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


def keyword_args(tool: str, text: str) -> dict[str, str]:
    """Arguments the LLM would have filled in, recovered from the text when there is no LLM."""
    t = _norm(text)
    if tool == "get_segment_insights":
        if re.search(r"\b(campanhas?|canal|canais|origem)\b", t):
            return {"dimension": "campaign"}
        if re.search(r"\b(motivos? de perda|por que perd\w+|perdemos)\b", t):
            return {"dimension": "loss_reason"}
    if tool == "get_systems_landscape":
        if re.search(r"\berps?\b", t):
            return {"category": "erp"}
        if re.search(r"\bcrms?\b", t):
            return {"category": "crm"}
    return {}
