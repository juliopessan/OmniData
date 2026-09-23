"""Routing decisions that need no LLM and no database (FR-BOT-7): who was addressed, team questions, keyword routes,
the insights overview split. Used by the orchestrator AND by `omnidata eval planner`, so the evaluation measures the real code."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ..agents import team as T
from ..agents.orion import Step, validate_plan
from ..llm.base import RouterResult
from .router import has_write_cue, keyword_route

NICK = re.compile(r"^\s*me chama de\s+(.{1,30}?)\s*[.!]?\s*$", re.IGNORECASE)
TEAM_Q = re.compile(r"\b(equipe|quem (sao|são) (voces|vocês)|quem trabalha|observatorio|observatório)\b", re.IGNORECASE)
INSIGHTS_Q = re.compile(r"\b(insights?|panorama das empresas|radar das empresas)\b", re.IGNORECASE)
# "me dá os insights": Orion splits it (Lyra: dores, Altair: demanda, Argus: cobertura)
OVERVIEW_PLAN: list[dict[str, Any]] = [{"agent": "lyra", "tool": "get_pains", "args": {}}, {"agent": "altair", "tool": "get_demand_types", "args": {}},
                 {"agent": "argus", "tool": "get_insight_coverage", "args": {}}]
_INTROS = ("quem é você", "quem e voce", "oi", "olá", "ola")
_NEEDS_INFO = re.compile(r"^\s*PRECISA_MAIS:\s*(\w+)", re.IGNORECASE)


@dataclass(frozen=True)
class Decision:
    kind: str                                  # nick | intro | team | plan | menu | not_mine
    steps: tuple[tuple[str, str], ...] = ()    # (agent, tool)
    other: str | None = None                   # not_mine: the agent that owns the tool


def pre_route(text: str) -> tuple[T.Agent | None, str, Decision | None]:
    """(addressed agent, text without the address, early decision). Early decisions never call an LLM."""
    if NICK.match(text):
        return None, text, Decision("nick")
    forced: T.Agent | None = None
    addr = T.parse_address(text)
    if addr:
        forced, text = addr
        if not text or text.lower().strip("?!. ") in _INTROS:
            return forced, text, Decision("intro")
    if forced is None and TEAM_Q.search(text):
        return None, text, Decision("team")
    return forced, text, None


def keyword_decision(text: str, forced: T.Agent | None) -> Decision:
    """The degraded route: one specialist by keyword, the insights overview, the tool owner's hand-off, or the menu."""
    tool = keyword_route(text)
    if tool is not None and has_write_cue(text):
        return Decision("menu")  # a write (or a write mixed with a read) needs the assistant online: never answer only the read half
    if tool is None and forced is None and INSIGHTS_Q.search(text):
        return Decision("plan", tuple((s["agent"], s["tool"]) for s in OVERVIEW_PLAN))
    if tool is None:
        return Decision("menu")
    if forced and T.TOOL_OWNER[tool] != forced.key:
        return Decision("not_mine", other=T.TOOL_OWNER[tool])
    return Decision("plan", ((T.TOOL_OWNER[tool], tool),))


def interpret_llm(res: RouterResult, forced: T.Agent | None) -> tuple[list[Step] | None, str]:
    """What the planner LLM's answer means. status: plan | rejected (invalid plan, never executed) | oos |
    needs_info:<agent> (in scope, but missing details to call a write tool) | none (fall back to keywords)."""
    if res.tool and res.tool.name == "plan":
        steps = validate_plan(res.tool.arguments.get("steps"), forced)
        return (steps, "plan") if steps else (None, "rejected")
    if res.tool and res.tool.name in T.TOOL_OWNER:  # a single direct tool call is also accepted
        steps = validate_plan([{"agent": T.TOOL_OWNER[res.tool.name], "tool": res.tool.name, "args": res.tool.arguments}], forced)
        return (steps, "plan") if steps else (None, "rejected")
    if res.text and "FORA_DO_ESCOPO" in res.text:
        return None, "oos"
    if res.text:
        m = _NEEDS_INFO.match(res.text)
        agent = m.group(1).lower() if m else None
        if agent and agent in T.SPECIALISTS and (forced is None or forced.key == agent):
            return None, f"needs_info:{agent}"
    return None, "none"
