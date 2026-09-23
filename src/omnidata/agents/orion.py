"""Orion: turns a request into a validated PLAN (<= 3 steps). The LLM proposes; this module disposes.
Every rule that keeps the harness safe is checked HERE, in code, not in a prompt."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..bot.tools import catalog
from .team import MAX_STEPS, SPECIALISTS, TOOL_OWNER, WRITE_TOOLS, Agent


def _tool_line(tool: str) -> str:
    """Lists each required arg, and — for a Literal/enum field — the exact accepted values: the `plan` tool's own JSON
    schema only constrains `agent`/`tool`, not `args` (kept a free object so one schema fits every tool), so this text
    description is the model's only source for which literal strings are valid. Found the hard way: `set_goal`'s
    `goal_type` was rejected twice in production because the model had no way to know "deals_won"/"quota_pct" verbatim."""
    model, desc = catalog.TOOLS[tool]
    props = model.model_json_schema().get("properties", {})
    req = model.model_json_schema().get("required", [])
    fields = [f"{name}: {'|'.join(props[name]['enum'])}" if "enum" in props.get(name, {}) else name for name in req]
    return f"  - {tool}({', '.join(fields)}): {desc}" if fields else f"  - {tool}: {desc}"


ORION_SYSTEM = (
    "Você é Orion, coordenador do Observatório, equipe de assessores de vendas no WhatsApp. Analise o pedido e chame a ferramenta "
    "`plan` com os passos, delegando cada passo ao especialista certo:\n"
    + "\n".join(f"- {a.key} ({a.title}):\n" + "\n".join(_tool_line(t) for t in a.tools) for a in SPECIALISTS.values())
    + "\nRegras: use o MENOR número de passos, quase sempre 1; só acrescente outro passo se o pedido tiver duas partes distintas. "
    "No máximo 3 passos e no máximo 1 que escreve no CRM, e ele deve ser o último. Nunca invente ids nem donos; não faça contas. "
    "Passe em `args` os argumentos entre parênteses (por exemplo, get_deal com o nome do negócio em `query`). "
    "Cumprimentos como “bom dia” e pedidos como “meu dia” vão para aurora.get_morning_brief. "
    "Um pedido geral por insights das empresas vai para lyra.get_pains, altair.get_demand_types e argus.get_insight_coverage. "
    "Pedidos para registrar, anotar ou resumir algo no CRM (ex.: “gera um resumo para o CRM”, “anota isso no negócio”) são "
    "trabalho da lyra.add_note, mesmo com essas palavras: se o pedido não disser claramente qual negócio e o que escrever, "
    "não chame a ferramenta nem responda FORA_DO_ESCOPO — responda apenas: PRECISA_MAIS:lyra (troque lyra pelo especialista "
    "certo se for outra ferramenta de escrita incompleta, como altair para uma alteração de negócio sem valor claro). "
    "Se o pedido não for sobre o trabalho de vendas, não chame ferramenta e responda apenas: FORA_DO_ESCOPO. "
    "Se a mensagem trouxer um bloco “Contexto da última troca”, é só pra você entender referências como “isso” ou "
    "“essas causas” que apontam pro que já foi dito — o que planejar vem só do “Pedido atual”, nunca do contexto sozinho."
)


@dataclass(frozen=True)
class Step:
    agent: str
    tool: str
    args: dict[str, Any]


def plan_schema() -> dict[str, Any]:
    tools = sorted(TOOL_OWNER)
    return {"name": "plan", "description": "Plano de atendimento: lista ordenada de passos, cada um delegado a um especialista.",
            "parameters": {"type": "object", "required": ["steps"], "properties": {"steps": {
                "type": "array", "minItems": 1, "maxItems": MAX_STEPS, "items": {
                    "type": "object", "required": ["agent", "tool"], "properties": {
                        "agent": {"type": "string", "enum": sorted(SPECIALISTS)},
                        "tool": {"type": "string", "enum": tools},
                        "args": {"type": "object"}}}}}}}


def validate_plan(raw: Any, forced: Agent | None = None) -> list[Step] | None:
    """None = reject the whole plan (caller falls back to the deterministic keyword route)."""
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_STEPS:
        return None
    steps: list[Step] = []
    for item in raw:
        if not isinstance(item, dict):
            return None
        agent, tool, args = item.get("agent"), item.get("tool"), item.get("args") or {}
        if agent not in SPECIALISTS or tool not in SPECIALISTS[agent].tools:      # allowlist per specialist
            return None
        if forced and agent != forced.key:                                       # user addressed one member
            return None
        parsed = catalog.validate(tool, args if isinstance(args, dict) else {})   # pydantic + owner args stripped
        if parsed is None:
            return None
        steps.append(Step(agent, tool, parsed.model_dump()))
    writes = [i for i, s in enumerate(steps) if s.tool in WRITE_TOOLS]
    if len(writes) > 1 or (writes and writes[0] != len(steps) - 1):               # <=1 write, and last
        return None
    return steps


def single_step(tool: str, args: dict[str, Any] | None = None) -> list[Step]:
    return [Step(TOOL_OWNER[tool], tool, catalog.validate(tool, args or {}).model_dump())]  # type: ignore[union-attr]
