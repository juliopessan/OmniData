"""Orion: turns a request into a validated PLAN (<= 3 steps). The LLM proposes; this module disposes.
Every rule that keeps the harness safe is checked HERE, in code, not in a prompt."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..bot.tools import catalog
from .team import MAX_STEPS, SPECIALISTS, TOOL_OWNER, WRITE_TOOLS, Agent

ORION_SYSTEM = (
    "Você é Orion, coordenador do Observatório, equipe de assessores de vendas no WhatsApp. Analise o pedido e chame a ferramenta "
    "`plan` com os passos, delegando cada passo ao especialista certo:\n"
    + "\n".join(f"- {a.key} ({a.title}): {', '.join(a.tools)}" for a in SPECIALISTS.values())
    + "\nRegras: no máximo 3 passos; no máximo 1 passo que escreve no CRM e ele deve ser o último; nunca invente ids nem donos; "
    "não faça contas. Se o pedido não for sobre o trabalho de vendas, não chame ferramenta e responda apenas: FORA_DO_ESCOPO."
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
