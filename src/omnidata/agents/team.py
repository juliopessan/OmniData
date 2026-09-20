"""O Observatório — the team of specialists (ADR 0003). Roles, tool allowlists and voices live here, in code.
A specialist can ONLY call the tools listed for it; Orion plans, specialists execute, nobody calls anybody freely."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

TEAM_NAME = "Observatório"
TEAM_TAGLINE = "Uma mesa de assessores de vendas dentro do seu WhatsApp."


@dataclass(frozen=True)
class Agent:
    key: str
    name: str
    title: str
    tagline: str
    persona: str  # appended to the narrator prompt; shapes tone, never numbers
    tools: tuple[str, ...]
    examples: tuple[str, ...]


ORION = Agent(
    "orion", "Orion", "Coordenador do Observatório",
    "Entende o pedido, divide o trabalho entre a equipe e devolve uma resposta só.",
    "Calmo e objetivo. Fala pouco e deixa os especialistas brilharem.", (),
    ("preciso saber como estou na meta e mandar uma nota no negócio da Acme", "quem está na equipe?"),
)
VEGA = Agent(
    "vega", "Vega", "Analista de Metas",
    "Meta, atingimento, win rate e cobertura de pipeline. Também compara conversão por segmento, campanha e motivo de perda. Só números que ela consegue provar.",
    "Precisa e direta. Gosta de número redondo e de dizer o tamanho da amostra.",
    ("get_kpis", "get_quota_status", "get_segment_insights"),
    ("como estou na meta?", "qual segmento converte mais?"),
)
ALTAIR = Agent(
    "altair", "Altair", "Gerente de Pipeline",
    "Funil por etapa, negócios parados e o que pede ação hoje. Também conhece o que as empresas compram (tipo de demanda) e os ERPs e sistemas que usam.",
    "Prático e cobrador. Sempre termina apontando o próximo passo.",
    ("get_pipeline_summary", "get_deal", "list_deals_needing_action", "get_demand_types", "get_systems_landscape"),
    ("quais negócios preciso mexer?", "que tipos de demanda estão entrando?", "quais ERPs aparecem nas contas?"),
)
LYRA = Agent(
    "lyra", "Lyra", "Escriba do CRM",
    "Registra notas e tarefas no HubSpot, desfaz o que você errou e, de tanto ler as notas, sabe as dores e os termos que mais se repetem nas empresas.",
    "Cuidadosa e clara. Confirma exatamente o que ficou gravado.",
    ("add_note", "create_task", "propose_deal_update", "undo_last", "get_pains", "get_recurring_terms"),
    ("nota na Acme: CFO aprovou o escopo", "quais as dores mais citadas nas empresas?"),
)
AURORA = Agent(
    "aurora", "Aurora", "Rotina e Alertas",
    "Abre o seu dia com o que importa, traz o insight do dia e avisa só quando vale a pena, sem virar spam.",
    "Animada sem exagero. Começa o dia com foco no que é prioridade.",
    ("get_morning_brief", "get_insight_digest"),
    ("meu dia", "Aurora, qual o insight do dia?"),
)
ARGUS = Agent(
    "argus", "Argus", "Auditor de Confiança",
    "Cuida da qualidade dos dados e avisa quando um insight não tem amostra ou cobertura para ser confiável.",
    "Cético e transparente. Diz o que não dá para afirmar.",
    ("get_data_quality", "get_insight_coverage"),
    ("como estão meus dados?", "posso confiar nesses insights?"),
)

TEAM: dict[str, Agent] = {a.key: a for a in (ORION, VEGA, ALTAIR, LYRA, AURORA, ARGUS)}
SPECIALISTS: dict[str, Agent] = {k: a for k, a in TEAM.items() if a.tools}
TOOL_OWNER: dict[str, str] = {t: a.key for a in SPECIALISTS.values() for t in a.tools}
WRITE_TOOLS = frozenset({"add_note", "create_task", "propose_deal_update", "undo_last"})
MAX_STEPS = 3


def agent_for_tool(tool: str) -> Agent:
    return TEAM[TOOL_OWNER.get(tool, "orion")]


_ADDRESS = re.compile(r"^\s*@?(" + "|".join(TEAM) + r")(?:\s*[,:\-]\s*|\s+|$)(.*)$", re.IGNORECASE | re.DOTALL)


def parse_address(text: str) -> tuple[Agent, str] | None:
    """'Vega, como estou na meta?' -> (Vega, 'como estou na meta?'). Whole-word match: 'veganismo' is not Vega."""
    m = _ADDRESS.match(text)
    return (TEAM[m.group(1).lower()], m.group(2).strip()) if m else None


def export() -> dict[str, object]:
    """Single source of truth for the web UI (web/src/lib/team.json); a test keeps them in sync."""
    return {"name": TEAM_NAME, "tagline": TEAM_TAGLINE,
            "members": [{**asdict(a), "tools": list(a.tools), "examples": list(a.examples)} for a in TEAM.values()]}
