"""Degraded-mode keyword router (FR-BOT-7): serves the top intents with no LLM."""
from __future__ import annotations

import re
import unicodedata

_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("get_playbook", re.compile(r"\b(script|abordagem|discurso de vendas|objecao|objecoes|quebrar? obje|quebra de obje|como (eu )?(respondo|convenco|argumento)|resposta pronta|pitch)\b")),
    ("search_meeting_notes", re.compile(r"\b(transcricao|transcricoes|na (ultima )?reuniao|na (ultima )?call|na (ultima )?ligacao)\b")),
    ("get_forecast", re.compile(r"\b(vou bater|vai bater|vamos bater|chances? de (eu |a gente |nos )?(bater|fechar|atingir)|probabilidade de (eu |a gente |nos )?(bater|fechar|ganhar|atingir)|forecast|(previsao|projecao|prever|previsto)( de| do| da| dos| das)? (a )?(meta|metas|fechamento|vendas|receita|faturamento|trimestre|mes|semana|pipeline|resultado|ganho))\b")),
    ("get_fix_queue", re.compile(r"\b(corri[gj]\w+|correcao|correcoes|preencher|arrumar|higiene|fila de correcao|o que (esta )?faltando|(dado|dados|campos?) faltando|sem valor|sem proximo passo)\b")),
    ("get_insight_digest", re.compile(r"\b(insight do dia|insight de hoje|destaque do dia)\b")),
    ("get_insight_coverage", re.compile(r"\b(cobertura|confiar nos insights?|insights? confiaveis?)\b")),
    ("get_pains", re.compile(r"\b(dores?|dificuldades? das empresas|problemas? (das|dos) (empresas|clientes)|(clientes|empresas)\b.{0,40}\b(relatam|reclamam|sentem))\b")),
    ("get_recurring_terms", re.compile(r"\b(termos?|palavras?|frases?|recorrentes?|se repete|se repetem)\b")),
    ("get_demand_types", re.compile(r"\b(demandas?|o que (as )?empresas (compram|pedem|buscam|estao pedindo|estao comprando|estao buscando))\b")),
    ("get_systems_landscape", re.compile(r"\b(erps?|sistemas?|totvs|sap|oracle|sankhya|protheus|concorrentes?)\b")),
    ("get_segment_insights", re.compile(r"\b(segmentos?|campanhas?|nichos?|motivos? de perda|por que perd\w+)\b")),
    ("get_team_status", re.compile(r"\b(time inteiro|equipe toda|status do time|status da equipe|quem esta (mais )?atras|ranking do time|prioridade de 1:1|prioridade de 1 a 1)\b")),
    ("get_goal_status", re.compile(r"\b(meta pessoal|meu objetivo)\b")),
    ("get_quota_status", re.compile(r"\b(metas?|quotas?|atingimento|falta quanto|quanto falta)\b")),
    ("get_data_quality", re.compile(r"\b(qualidade|confiavel|confiar|meus dados|amostra)\b")),
    ("get_kpis", re.compile(r"\b(numeros?|kpis?|win ?rate|conversao|taxa de ganho|meus? resultados?)\b")),
    ("list_deals_needing_action", re.compile(r"\b(acao|atencao|parados?|prioridades?|precisam|urgente|o que fazer|mexer|mexo|focar|foco|priorizar)\b")),
    ("get_pipeline_summary", re.compile(r"\b(pipeline|funil|etapas?|quantos negocios)\b")),
    ("get_morning_brief", re.compile(r"\b(meu dia|resumo|bom dia|brief|hoje)\b")),
]


def _norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


# Looking a deal up by name ("negócio da Fast Shop"). The name is taken from the ORIGINAL text (accents matter for the ILIKE search).
_NOT_A_DEAL = re.compile(r"^(meu|minha|meus|minhas|semana|m[eê]s|dia|hoje|time|equipe|carteira|funil|pipeline)\b", re.IGNORECASE)
_DEAL_SPECIFIC = [
    re.compile(r"\b(?:neg[óo]cio|deal|conta)\s+(?:da|do|de)\s+(?P<q>[^?!.]+)", re.IGNORECASE),
    re.compile(r"\bdetalhes?\s+(?:do|da)\s+(?:deal|neg[óo]cio)\s+(?P<q>[^?!.]+)", re.IGNORECASE),
    re.compile(r"\b(?:valor|etapa|fase|status)(?:\s+e\s+(?:a|o)\s+(?:valor|etapa|fase|status))?\s+(?:da|do)\s+(?P<q>[^?!.]+)", re.IGNORECASE),
]
_DEAL_LOOSE = re.compile(r"\bcomo\s+est[áa]\s+(?:o|a)\s+(?P<q>[^?!.]+)", re.IGNORECASE)
# A request that WRITES to the CRM needs the assistant online (confirmation, receipt, undo). Without an LLM we never answer half of it.
_WRITE_CUE = re.compile(r"\b(anota\w*|anote\w*|registra\w*|coloca\w*|escreve\w*|adiciona\w*|agenda\w*|joga\w* (uma )?(nota|observacao)|cria\w* (uma )?tarefa|muda\w*|mude\w*|alter\w*|passa\w* (o )?negocio|move\w*|desfaz\w*|desfa[cç]a|nota (na|no|do|da) )", re.IGNORECASE)


# A deal is looked up only by a QUESTION or a read verb; a statement ("deixa uma observação no deal X: ...") is probably a write, and the
# degraded mode must not answer it as a read (the user would think it was saved).
_READ_START = re.compile(r"^\s*(me )?(fala|falar|mostra|mostre|diz|conta|traz|qual|quais|como|quanto|quantos|quantas|o que|detalhes?|cade|onde)\b")


def _is_question(text: str) -> bool:
    return "?" in text or bool(_READ_START.match(_norm(text)))


def deal_query(text: str, loose: bool = False) -> str | None:
    if not _is_question(text):
        return None
    for rx in ([_DEAL_LOOSE] if loose else _DEAL_SPECIFIC):
        m = rx.search(text)
        if m:
            q = m.group("q").strip()[:120]
            if len(q) >= 2 and not _NOT_A_DEAL.match(q):
                return q
    return None


def has_write_cue(text: str) -> bool:
    return bool(_WRITE_CUE.search(_norm(text)))


def keyword_route(text: str) -> str | None:
    t = _norm(text)
    if deal_query(text):
        return "get_deal"
    for tool, rx in _RULES:
        if rx.search(t):
            return tool
    return "get_deal" if deal_query(text, loose=True) else None


def keyword_args(tool: str, text: str) -> dict[str, str]:
    """Arguments the LLM would have filled in, recovered from the text when there is no LLM."""
    t = _norm(text)
    if tool == "get_deal":
        q = deal_query(text) or deal_query(text, loose=True)
        return {"query": q} if q else {}
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
    if tool == "get_playbook":
        if re.search(r"\bdor(es)?\b", t):
            return {"topic": "pain"}
        if re.search(r"\b(script|abordagem|discurso de vendas|pitch)\b", t):
            return {"topic": "pitch"}
    if tool == "search_meeting_notes":
        return {"query": text[:200]}
    return {}
