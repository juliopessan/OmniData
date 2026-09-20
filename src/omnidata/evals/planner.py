"""Planner evaluation: does Orion send a request to the right specialist and tool? Deterministic scoring, no judge model.
Two modes over the same golden set (planner_cases.yaml):
  keyword  the degraded route (no LLM); runs anywhere, in CI
  llm      the real planner LLM (needs a key); compares the validated plan with the ideal one
Outcomes: correct | acceptable (menu instead of a plan, allowed for cases only an LLM can do) | extra (right steps plus unrequested reads) | partial (answered only some of several reads) |
miss (menu, should have answered) | wrong (answered with another plan: worse than a menu) | critical (a CRM write nobody asked for).
CAUTION: the keyword rules were tuned on this same set, so a high keyword score shows no regression, not generalisation.
Measure generalisation with phrases the rules have never seen (real WhatsApp messages, once they exist)."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ..agents import team as T
from ..agents.orion import ORION_SYSTEM, plan_schema
from ..bot.routing import Decision, interpret_llm, keyword_decision, pre_route
from ..llm.base import LlmClient
from ..security.pii_masking import mask_pii

CASES_FILE = Path(__file__).with_name("planner_cases.yaml")
Steps = tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class Case:
    id: str
    tag: str
    text: str
    kind: str = "plan"
    plan: Steps = ()
    menu_ok: bool = False


@dataclass
class Result:
    case: Case
    got: str                 # rendered outcome, e.g. "plan vega.get_kpis" | "menu" | "oos"
    outcome: str


@dataclass
class Report:
    mode: str
    results: list[Result] = field(default_factory=list)

    def count(self, outcome: str) -> int:
        return sum(1 for r in self.results if r.outcome == outcome)

    @property
    def total(self) -> int:
        return len(self.results)

    def rate(self, *outcomes: str) -> float:
        return sum(self.count(o) for o in outcomes) / self.total if self.total else 0.0

    def by_tag(self) -> dict[str, dict[str, int]]:
        tags: dict[str, Counter[str]] = defaultdict(Counter)
        for r in self.results:
            tags[r.case.tag][r.outcome] += 1
            tags[r.case.tag]["n"] += 1
        return {t: dict(c) for t, c in tags.items()}

    def to_json(self) -> dict[str, Any]:
        return {"mode": self.mode, "total": self.total, "correct": self.rate("correct"), "correct_or_acceptable": self.rate("correct", "acceptable"),
                "counts": {o: self.count(o) for o in ("correct", "acceptable", "extra", "partial", "miss", "wrong", "critical")}, "by_tag": self.by_tag(),
                "failures": [{"id": r.case.id, "text": r.case.text, "expected": render(r.case), "got": r.got, "outcome": r.outcome}
                             for r in self.results if r.outcome in ("extra", "partial", "miss", "wrong", "critical")]}


def _steps(raw: list[str]) -> Steps:
    return tuple((a, t) for a, _, t in (s.partition(".") for s in raw))


def load_cases(path: Path = CASES_FILE) -> list[Case]:
    cases = [Case(c["id"], c["tag"], c["text"], c.get("kind", "plan"), _steps(c.get("plan", [])), bool(c.get("menu_ok", False)))
             for c in yaml.safe_load(path.read_text(encoding="utf-8"))]
    ids = [c.id for c in cases]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate case ids")
    return cases


def render(case: Case) -> str:
    return f"plan {' > '.join(f'{a}.{t}' for a, t in case.plan)}" if case.kind == "plan" else case.kind


def _render_decision(d: Decision) -> str:
    return f"plan {' > '.join(f'{a}.{t}' for a, t in d.steps)}" if d.kind == "plan" else d.kind


def judge(case: Case, kind: str, steps: Steps) -> str:
    """Compare what the system did (kind: plan | menu | oos | intro | team | nick | not_mine) with the ideal outcome."""
    wrote = any(t in T.WRITE_TOOLS for _, t in steps)
    ideal_writes = any(t in T.WRITE_TOOLS for _, t in case.plan)
    if kind == "plan" and wrote and not ideal_writes:
        return "critical"                                   # a write nobody asked for
    if case.kind == "plan":
        if kind == "plan":
            if steps == case.plan:
                return "correct"
            if not ideal_writes and steps and set(steps) < set(case.plan):
                return "partial"                            # answered only part of a multi-read request: incomplete, not misleading
            if set(case.plan) < set(steps) and not any(t in T.WRITE_TOOLS for _, t in steps if (_, t) not in case.plan):
                return "extra"                              # the right steps plus unrequested READS: wordy and slower, not misleading
            return "wrong"
        if kind in ("menu", "oos"):
            return "acceptable" if case.menu_ok else "miss"
        return "wrong"
    if case.kind == "oos":                                  # menu (degraded) and FORA_DO_ESCOPO (LLM) are both right
        return "correct" if kind in ("menu", "oos") else "wrong"
    return "correct" if kind == case.kind else "wrong"


def keyword_outcome(text: str) -> Decision:
    forced, stripped, early = pre_route(text)
    return early or keyword_decision(stripped, forced)


def run_keyword(cases: list[Case]) -> Report:
    rep = Report("keyword")
    for c in cases:
        d = keyword_outcome(c.text)
        rep.results.append(Result(c, _render_decision(d), judge(c, d.kind, d.steps)))
    return rep


async def run_llm(cases: list[Case], llm: LlmClient) -> Report:
    rep = Report("llm")
    for c in cases:
        forced, stripped, early = pre_route(c.text)
        if early:
            rep.results.append(Result(c, _render_decision(early), judge(c, early.kind, ())))
            continue
        res = await llm.route(ORION_SYSTEM, mask_pii(stripped), [plan_schema()])
        steps, status = interpret_llm(res, forced)
        if steps:
            got: Steps = tuple((s.agent, s.tool) for s in steps)
            rep.results.append(Result(c, _render_decision(Decision("plan", got)), judge(c, "plan", got)))
        elif status == "oos":
            rep.results.append(Result(c, "oos", judge(c, "oos", ())))
        else:                                               # rejected / no tool: the bot falls back to the keyword route, so do we
            d = keyword_decision(stripped, forced)
            rep.results.append(Result(c, f"{status} → {_render_decision(d)}", judge(c, d.kind, d.steps)))
    return rep


def format_report(rep: Report) -> str:
    lines = [f"planner eval · mode={rep.mode} · {rep.total} cases",
             f"correct {rep.rate('correct'):.0%} · correct or acceptable {rep.rate('correct', 'acceptable'):.0%} · "
             f"extra {rep.count('extra')} · partial {rep.count('partial')} · miss {rep.count('miss')} · wrong {rep.count('wrong')} · critical {rep.count('critical')}", "", "by tag:"]
    for tag, c in sorted(rep.by_tag().items()):
        lines.append(f"  {tag:<14} {c.get('correct', 0) + c.get('acceptable', 0)}/{c['n']}  (extra {c.get('extra', 0)}, partial {c.get('partial', 0)}, miss {c.get('miss', 0)}, wrong {c.get('wrong', 0)}, critical {c.get('critical', 0)})")
    bad = [r for r in rep.results if r.outcome in ("extra", "partial", "miss", "wrong", "critical")]
    if rep.mode == "keyword":
        lines += ["", "note: the keyword rules were tuned on this set; use new phrases to measure generalisation."]
    if bad:
        lines += ["", "failures:"]
        lines += [f"  [{r.outcome}] {r.case.id}: “{r.case.text}”\n      expected {render(r.case)} · got {r.got}" for r in bad]
    return "\n".join(lines)
